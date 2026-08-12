"""
dimensional_model_etl DAG (adrs/0008-dimensional-modeling.md)

raw_events 를 Star Schema(dim_date/dim_product/dim_user + fact_events)로
변환한다. daily_etl(단순 집계)과 별도 DAG으로 분리한 이유: 이 DAG은
분석/BI 용도의 스키마를 소유하고, daily_etl은 운영 대시보드용 집계를
소유한다 - 서로 목적이 다른 결과물이라 독립적으로 재실행/실패해도
되게 분리했다.

이 DAG이 만지는 테이블은 FastAPI 애플리케이션의 SQLAlchemy 모델
(app/models.py, OLTP 스키마)과 별개다. 분석용 스키마(DW 레이어)는
데이터 파이프라인이 소유하고, 애플리케이션 스키마는 Alembic이
소유하는 것으로 책임을 나눴다.

파이프라인 단계:
  1. ensure_dimensional_tables : DDL (없으면 생성)
  2. load_dim_date             : 대상 날짜의 dim_date 행 upsert
  3. load_dim_scd2             : dim_product/dim_user를 Type 2 SCD로 갱신
  4. load_fact_events          : raw_events -> fact_events 변환 적재

모든 단계는 같은 날짜(ds)에 대해 여러 번 실행돼도 결과가 같아야
한다(멱등성, adrs/0010-airflow-pipeline-reliability.md 에서 재시도를
도입할 예정이라 이 성질이 필수).
"""
from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sensors.external_task import ExternalTaskSensor

CONN_ID = "projecte_db"


def ensure_dimensional_tables(**_):
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        """
        CREATE TABLE IF NOT EXISTS dim_date (
            date_key     INTEGER PRIMARY KEY,
            full_date    DATE NOT NULL UNIQUE,
            year         INTEGER NOT NULL,
            month        INTEGER NOT NULL,
            day          INTEGER NOT NULL,
            day_of_week  INTEGER NOT NULL,
            is_weekend   BOOLEAN NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_product (
            product_key      SERIAL PRIMARY KEY,
            product_id       TEXT NOT NULL,
            description      TEXT,
            price            DOUBLE PRECISION,
            effective_date   TIMESTAMP NOT NULL DEFAULT now(),
            expiration_date  TIMESTAMP,
            is_current       BOOLEAN NOT NULL DEFAULT true
        );
        CREATE INDEX IF NOT EXISTS ix_dim_product_current
            ON dim_product (product_id) WHERE is_current;

        CREATE TABLE IF NOT EXISTS dim_user (
            user_key         SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL,
            country          TEXT,
            effective_date   TIMESTAMP NOT NULL DEFAULT now(),
            expiration_date  TIMESTAMP,
            is_current       BOOLEAN NOT NULL DEFAULT true
        );
        CREATE INDEX IF NOT EXISTS ix_dim_user_current
            ON dim_user (user_id) WHERE is_current;

        CREATE TABLE IF NOT EXISTS fact_events (
            event_key        BIGSERIAL PRIMARY KEY,
            date_key         INTEGER REFERENCES dim_date(date_key),
            product_key      INTEGER REFERENCES dim_product(product_key),
            user_key         INTEGER REFERENCES dim_user(user_key),
            event_type       TEXT NOT NULL,
            price            DOUBLE PRECISION,
            revenue          DOUBLE PRECISION NOT NULL DEFAULT 0,
            source_event_id  BIGINT NOT NULL UNIQUE
        );
        CREATE INDEX IF NOT EXISTS ix_fact_events_date ON fact_events (date_key);
        CREATE INDEX IF NOT EXISTS ix_fact_events_product ON fact_events (product_key);
        """
    )


def load_dim_date(**context):
    """
    대상 날짜(ds) 하나의 dim_date 행을 upsert. date_key는 YYYYMMDD
    정수로 둔다(조회 시 사람이 읽기 쉽고, 파티션 키로도 흔히 쓰이는
    관례적인 형식).
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        """
        INSERT INTO dim_date (date_key, full_date, year, month, day, day_of_week, is_weekend)
        SELECT
            TO_CHAR(%(ds)s::date, 'YYYYMMDD')::int,
            %(ds)s::date,
            EXTRACT(YEAR FROM %(ds)s::date)::int,
            EXTRACT(MONTH FROM %(ds)s::date)::int,
            EXTRACT(DAY FROM %(ds)s::date)::int,
            EXTRACT(ISODOW FROM %(ds)s::date)::int,
            EXTRACT(ISODOW FROM %(ds)s::date)::int IN (6, 7)
        ON CONFLICT (date_key) DO NOTHING;
        """,
        parameters={"ds": ds},
    )


def load_dim_scd2(**context):
    """
    dim_product, dim_user를 Type 2 SCD로 갱신한다.

    대상 날짜(ds)에 등장한 상품/사용자 각각에 대해:
      1. 현재(is_current=true) 버전과 최신 속성(products/users 테이블
         기준)을 비교
      2. 속성이 다르면: 기존 버전을 만료(is_current=false,
         expiration_date=now) + 새 버전을 삽입(is_current=true)
      3. 자연키가 아예 처음 등장하면: 새 버전만 삽입
      4. 속성이 같으면: 아무것도 안 함 (이미 최신 버전이 정확함)

    "대상 날짜에 등장한 것만" 비교 대상으로 좁히는 이유: 매번 전체
    상품/사용자를 다 비교하면 배치가 갈수록 느려진다. 그날 실제로
    이벤트가 발생한 것만 보면 충분하다.
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    # --- dim_product ---
    changed_products = hook.get_records(
        """
        SELECT p.product_id, p.description, p.price
        FROM products p
        JOIN (
            SELECT DISTINCT product_id FROM raw_events
            WHERE timestamp::date = %(ds)s AND product_id IS NOT NULL
        ) touched ON touched.product_id = p.product_id
        LEFT JOIN dim_product dp
            ON dp.product_id = p.product_id AND dp.is_current
        WHERE dp.product_id IS NULL                      -- 처음 등장
           OR dp.description IS DISTINCT FROM p.description
           OR dp.price IS DISTINCT FROM p.price;          -- 속성이 바뀜
        """,
        parameters={"ds": ds},
    )
    for product_id, description, price in changed_products:
        hook.run(
            """
            UPDATE dim_product SET is_current = false, expiration_date = now()
            WHERE product_id = %(pid)s AND is_current;

            INSERT INTO dim_product (product_id, description, price)
            VALUES (%(pid)s, %(desc)s, %(price)s);
            """,
            parameters={"pid": product_id, "desc": description, "price": price},
        )

    # --- dim_user ---
    changed_users = hook.get_records(
        """
        SELECT u.user_id, u.country
        FROM users u
        JOIN (
            SELECT DISTINCT user_id FROM raw_events
            WHERE timestamp::date = %(ds)s AND user_id IS NOT NULL
        ) touched ON touched.user_id = u.user_id
        LEFT JOIN dim_user du
            ON du.user_id = u.user_id AND du.is_current
        WHERE du.user_id IS NULL
           OR du.country IS DISTINCT FROM u.country;
        """,
        parameters={"ds": ds},
    )
    for user_id, country in changed_users:
        hook.run(
            """
            UPDATE dim_user SET is_current = false, expiration_date = now()
            WHERE user_id = %(uid)s AND is_current;

            INSERT INTO dim_user (user_id, country)
            VALUES (%(uid)s, %(country)s);
            """,
            parameters={"uid": user_id, "country": country},
        )


def load_fact_events(**context):
    """
    대상 날짜(ds)의 raw_events를 fact_events로 변환 적재.

    - source_event_id 에 UNIQUE 제약을 걸어뒀으므로(ensure_
      dimensional_tables), ON CONFLICT DO NOTHING 으로 재실행해도
      중복 적재되지 않는다 (멱등성).
    - 그 시점 "현재(is_current=true)" 차원 버전의 surrogate key를
      조인해서 가져온다 - Type 2 SCD의 핵심: 이 배치가 도는 시점의
      현재 버전을 붙이므로, 나중에 차원 속성이 바뀌어도 이미 적재된
      과거 사실 행은 그 시점 값을 그대로 유지한다.
    - quarantine_events 에 있는 source_event_id는 제외한다
      (adrs/0009-data-quality-validation.md). raw_events 원본은
      건드리지 않고, 이 적재 단계에서만 걸러낸다.
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        """
        INSERT INTO fact_events
            (date_key, product_key, user_key, event_type, price, revenue, source_event_id)
        SELECT
            TO_CHAR(re.timestamp::date, 'YYYYMMDD')::int,
            dp.product_key,
            du.user_key,
            re.event_type,
            re.price,
            CASE WHEN re.event_type = 'purchase' THEN COALESCE(re.price, 0) ELSE 0 END,
            re.id
        FROM raw_events re
        LEFT JOIN dim_product dp ON dp.product_id = re.product_id AND dp.is_current
        LEFT JOIN dim_user du ON du.user_id = re.user_id AND du.is_current
        WHERE re.timestamp::date = %(ds)s
          AND NOT EXISTS (
              SELECT 1 FROM quarantine_events qe WHERE qe.source_event_id = re.id
          )
        ON CONFLICT (source_event_id) DO NOTHING;
        """,
        parameters={"ds": ds},
    )


with DAG(
    dag_id="dimensional_model_etl",
    description="raw_events -> Star Schema(dim_date/product/user, fact_events) 변환",
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    tags=["projecte", "batch", "dimensional-model"],
) as dag:

    # data_quality_check DAG이 같은 논리 날짜(execution_date)에 대해
    # 끝날 때까지 대기 (adrs/0009-data-quality-validation.md). 두 DAG을
    # 독립적으로 재실행/모니터링할 수 있게 분리했으므로, 순서 보장은
    # 이 센서로 명시적으로 건다 - 그래야 load_fact_events가 참조하는
    # quarantine_events가 그날 검증까지 반영된 최신 상태임을 보장한다.
    wait_for_quality_check = ExternalTaskSensor(
        task_id="wait_for_quality_check",
        external_dag_id="data_quality_check",
        external_task_id="validate_events",
        allowed_states=["success"],
        timeout=600,
        poke_interval=30,
    )

    t1 = PythonOperator(task_id="ensure_dimensional_tables", python_callable=ensure_dimensional_tables)
    t2 = PythonOperator(task_id="load_dim_date", python_callable=load_dim_date)
    t3 = PythonOperator(task_id="load_dim_scd2", python_callable=load_dim_scd2)
    t4 = PythonOperator(task_id="load_fact_events", python_callable=load_fact_events)

    # dim_date/dim_scd2 는 서로 독립적이라 병렬 실행 가능,
    # 둘 다 끝난 뒤에 fact_events 적재(차원 키가 준비되어 있어야 함 -
    # fact_events.date_key 가 dim_date를 FK로 참조하므로, load_dim_date가
    # 먼저 그 날짜 행을 넣어두지 않으면 FK 제약 위반으로 insert가 실패한다).
    # quarantine_events를 참조하는 load_fact_events는 품질 검증 완료
    # 이후에만 실행되어야 하므로 센서도 함께 건다.
    t1 >> [t2, t3]
    [t2, t3, wait_for_quality_check] >> t4