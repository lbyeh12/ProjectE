"""
data_quality_check DAG (adrs/0009-data-quality-validation.md)

raw_events 를 검증해서 불량 데이터를 quarantine_events 로 격리한다.
raw_events 원본은 건드리지 않는다 - "원본 로그는 손대지 않는다"는
원칙을 지키기 위해서다(감사/디버깅 목적으로 항상 원본을 보존).
대신 다운스트림(dimensional_model_etl, daily_etl)이 격리된
source_event_id 를 걸러내고 읽도록 한다.

검증 규칙은 Great Expectations(1.x, Fluent/Core API)로 선언하고,
위반 건수 리포트를 로그로 남긴다. GE 호출은 try/except로 감싸서,
API 버전 차이 등으로 GE 쪽이 실패해도 격리 로직 자체는 항상
정상 동작한다 - GE는 "있으면 좋은 리포트"이지 격리 기능의 필수
전제가 아니다. "정확히 어느 행을 격리할지"는 pandas 불리언 마스크로
직접 판정한다 - GE의 결과 딕셔너리 구조에 격리라는 중요한 동작을
의존시키지 않기로 했다. 즉 GE는 "규칙을 선언하고 위반을 리포트하는"
역할, 격리 판정 자체는 이 마스크가 담당하도록 역할을 나눴다.

검증 규칙:
  - price >= 0
  - timestamp <= 현재 시각
  - user_id가 있으면 users 테이블에 존재해야 함 (참조 무결성)
  - product_id가 있으면 products 테이블에 존재해야 함 (참조 무결성)

한 행이 여러 규칙을 동시에 위반해도, 사유는 하나만(가장 먼저 걸린
규칙) 기록한다 - 격리 사유를 "제일 근본적인 문제 하나"로 단순하게
읽을 수 있게 하기 위함.
"""
from __future__ import annotations

import pandas as pd
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

from dag_common import DEFAULT_ARGS, notify_failure_slack

CONN_ID = "projecte_db"


def ensure_quarantine_table(**_):
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        """
        CREATE TABLE IF NOT EXISTS quarantine_events (
            source_event_id  BIGINT PRIMARY KEY,
            user_id          INTEGER,
            event_type       TEXT,
            product_id       TEXT,
            price            DOUBLE PRECISION,
            timestamp        TIMESTAMP,
            quarantine_reason TEXT NOT NULL,
            quarantined_at   TIMESTAMP NOT NULL DEFAULT now()
        );
        """
    )


def validate_events(**context):
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    df = hook.get_pandas_df(
        """
        SELECT id, user_id, event_type, product_id, price, timestamp
        FROM raw_events
        WHERE timestamp::date = %(ds)s
        """,
        parameters={"ds": ds},
    )
    if df.empty:
        print("[data_quality_check] 대상 이벤트 없음, 검증 스킵")
        return

    known_user_ids = set(hook.get_pandas_df("SELECT user_id FROM users")["user_id"])
    known_product_ids = set(hook.get_pandas_df("SELECT product_id FROM products")["product_id"])
    now = pd.Timestamp.utcnow().tz_localize(None)

    # --- Great Expectations: 규칙을 선언적으로 검증하고 위반 건수를 리포트 ---
    # GE 1.x(Fluent/Core API)를 쓴다. 이 환경에서 정확한 API 동작을
    # 사전에 실행 검증할 수 없어서(네트워크 제약), 혹시 API가 조금
    # 달라져 있어도 아래 try/except가 실패를 흡수해 로그만 남기고,
    # 핵심 로직(바로 다음의 pandas 격리 판정)은 GE 성공 여부와 무관하게
    # 항상 그대로 실행되게 만들었다 - GE는 "있으면 좋은 리포트"이지
    # 격리 기능의 필수 전제가 아니다.
    try:
        import great_expectations as gx

        context = gx.get_context(mode="ephemeral")
        data_source = context.data_sources.add_pandas(name="raw_events_source")
        data_asset = data_source.add_dataframe_asset(name="raw_events_asset")
        batch_definition = data_asset.add_batch_definition_whole_dataframe("daily_batch")
        batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

        price_check = gx.expectations.ExpectColumnValuesToBeBetween(column="price", min_value=0)
        ts_check = gx.expectations.ExpectColumnValuesToBeBetween(column="timestamp", max_value=now)

        price_result = batch.validate(price_check)
        ts_result = batch.validate(ts_check)
        print(
            f"[GE] price>=0 위반 {price_result['result'].get('unexpected_count', 0)}건, "
            f"timestamp<=now 위반 {ts_result['result'].get('unexpected_count', 0)}건"
        )
    except Exception as e:
        print(f"[GE] 검증 리포트 생성 중 오류(격리 로직에는 영향 없음): {e}")

    # --- 격리 판정: pandas 마스크로 직접, 명확하게 계산 ---
    reasons = pd.Series([None] * len(df), index=df.index, dtype=object)

    def mark(mask, reason):
        target = mask & reasons.isna()
        reasons.loc[target] = reason

    mark(df["price"].notna() & (df["price"] < 0), "price_negative")
    mark(df["timestamp"] > now, "timestamp_future")
    mark(df["user_id"].notna() & ~df["user_id"].isin(known_user_ids), "unknown_user_id")
    mark(df["product_id"].notna() & ~df["product_id"].isin(known_product_ids), "unknown_product_id")

    df["quarantine_reason"] = reasons
    quarantined = df[df["quarantine_reason"].notna()]

    print(f"[data_quality_check] 총 {len(df)}건 중 {len(quarantined)}건 격리")
    if quarantined.empty:
        return

    # 이미 격리된 적 있는 건 다시 넣지 않도록(재시도 시 멱등) ON CONFLICT 사용.
    for _, row in quarantined.iterrows():
        hook.run(
            """
            INSERT INTO quarantine_events
                (source_event_id, user_id, event_type, product_id, price, timestamp, quarantine_reason)
            VALUES (%(id)s, %(user_id)s, %(event_type)s, %(product_id)s, %(price)s, %(timestamp)s, %(reason)s)
            ON CONFLICT (source_event_id) DO NOTHING;
            """,
            parameters={
                "id": row["id"],
                "user_id": None if pd.isna(row["user_id"]) else int(row["user_id"]),
                "event_type": row["event_type"],
                "product_id": row["product_id"],
                "price": None if pd.isna(row["price"]) else float(row["price"]),
                "timestamp": row["timestamp"],
                "reason": row["quarantine_reason"],
            },
        )


with DAG(
    dag_id="data_quality_check",
    description="raw_events 검증, 불량 데이터를 quarantine_events로 격리",
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    on_failure_callback=notify_failure_slack,
    tags=["projecte", "batch", "data-quality"],
) as dag:

    t1 = PythonOperator(task_id="ensure_quarantine_table", python_callable=ensure_quarantine_table)
    t2 = PythonOperator(task_id="validate_events", python_callable=validate_events)

    # 검증이 끝나면 dimensional_model_etl을 바로 자동으로 실행시킨다.
    # 처음엔 ExternalTaskSensor로 두 DAG을 나중에 맞춰 연결하는 방식을
    # 썼는데, 이 방식은 "정확히 같은 logical_date(초 단위까지 일치)"를
    # 요구해서, 수동으로 각 DAG을 서로 다른 시각에 트리거하면 센서가
    # 영원히 대기하는 문제를 실제로 겪었다. TriggerDagRunOperator로
    # "이 DAG이 끝나면 다음 DAG을 직접 실행시키는" 체인으로 바꾸면,
    # 사람이 맨 앞의 DAG 하나만 트리거해도 나머지가 자동으로 이어져서
    # 이 문제 자체가 생기지 않는다.
    trigger_next = TriggerDagRunOperator(
        task_id="trigger_dimensional_model_etl",
        trigger_dag_id="dimensional_model_etl",
        logical_date="{{ logical_date }}",  # 같은 논리 날짜를 그대로 전달
        wait_for_completion=False,  # "실행시키기"만 하고 바로 끝남 (fire-and-forget)
    )

    t1 >> t2 >> trigger_next