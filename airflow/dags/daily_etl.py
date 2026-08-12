"""
daily_etl DAG

매일 한 번 실행되어 raw_events 를 기반으로 일별 지표를 계산하고
daily_metrics 테이블에 저장한다.

계산 지표:
  - DAU (Daily Active Users)   : 그날 활동한 순 사용자 수
  - Conversion Rate             : 그날 view 대비 purchase 비율
  - revenue                     : 그날 총 매출 (purchase price 합)
  - event_count                 : 그날 총 이벤트 수

파이프라인 단계 (Extract → Transform → Load 패턴):
  1. ensure_table   : 결과 테이블이 없으면 생성
  2. compute_metrics: 대상 날짜의 지표 계산 후 upsert
  3. report         : 결과를 로그로 출력

이 DAG은 Airflow가 관리하는 애플리케이션 DB(projecte)의 raw_events 를 읽는다.
raw_events 는 Spark Streaming 이 채운다.
"""
from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

from dag_common import DEFAULT_ARGS, notify_failure_slack

# raw_events 가 들어있는 애플리케이션 DB에 연결하기 위한 Airflow Connection ID.
# docker-compose 에서 환경변수(AIRFLOW_CONN_PROJECTE_DB)로 주입한다.
CONN_ID = "projecte_db"


def ensure_table(**_):
    """일별 지표 결과 테이블 생성 (없으면)."""
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        """
        CREATE TABLE IF NOT EXISTS daily_metrics (
            metric_date   DATE PRIMARY KEY,
            dau           BIGINT,
            view_count    BIGINT,
            purchase_count BIGINT,
            conversion_rate DOUBLE PRECISION,
            revenue       DOUBLE PRECISION,
            event_count   BIGINT
        );

        -- data_quality_check DAG(adrs/0009)이 소유한 테이블이지만,
        -- 이 DAG이 그보다 먼저 실행돼도 아래 쿼리가 깨지지 않도록
        -- 여기서도 동일하게 보장해둔다(idempotent CREATE IF NOT EXISTS
        -- 라 두 DAG이 서로 다른 순서로 실행돼도 안전하다).
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


def compute_metrics(**context):
    """
    실행 대상 날짜(ds)의 지표를 계산해서 daily_metrics 에 upsert.
    ds 는 Airflow 가 넣어주는 실행 논리 날짜(YYYY-MM-DD).
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    # 하나의 쿼리로 그날의 모든 지표를 계산한다.
    # raw_events.timestamp 의 날짜가 ds 와 같은 행만 대상으로 한다.
    sql = """
        WITH day_events AS (
            SELECT *
            FROM raw_events re
            WHERE timestamp::date = %(ds)s
              AND NOT EXISTS (
                  -- adrs/0009-data-quality-validation.md: 격리된 이벤트는
                  -- 운영 지표(DAU/전환율/매출)에도 반영하지 않는다.
                  -- 이 DAG은 data_quality_check와 하드 의존성(센서)을
                  -- 걸지 않고, "그 시점 quarantine_events 테이블 상태
                  -- 기준으로 최선을 다해 제외"하는 정도로만 다룬다 -
                  -- 운영 대시보드용 요약이라 dimensional_model_etl의
                  -- fact_events(분석 레이어, 엄격한 순서 보장)보다는
                  -- 낮은 엄격도로 충분하다고 판단했다.
                  SELECT 1 FROM quarantine_events qe WHERE qe.source_event_id = re.id
              )
        )
        SELECT
            COUNT(DISTINCT user_id)                                          AS dau,
            COUNT(*) FILTER (WHERE event_type = 'view')                       AS view_count,
            COUNT(*) FILTER (WHERE event_type = 'purchase')                   AS purchase_count,
            COALESCE(SUM(price) FILTER (WHERE event_type = 'purchase'), 0)    AS revenue,
            COUNT(*)                                                          AS event_count
        FROM day_events;
    """
    row = hook.get_first(sql, parameters={"ds": ds})
    dau, view_count, purchase_count, revenue, event_count = row

    conversion_rate = (purchase_count / view_count) if view_count else 0.0

    # upsert: 같은 날짜가 이미 있으면 갱신
    hook.run(
        """
        INSERT INTO daily_metrics
            (metric_date, dau, view_count, purchase_count, conversion_rate, revenue, event_count)
        VALUES (%(ds)s, %(dau)s, %(view)s, %(purchase)s, %(conv)s, %(rev)s, %(events)s)
        ON CONFLICT (metric_date) DO UPDATE SET
            dau = EXCLUDED.dau,
            view_count = EXCLUDED.view_count,
            purchase_count = EXCLUDED.purchase_count,
            conversion_rate = EXCLUDED.conversion_rate,
            revenue = EXCLUDED.revenue,
            event_count = EXCLUDED.event_count;
        """,
        parameters={
            "ds": ds, "dau": dau, "view": view_count, "purchase": purchase_count,
            "conv": conversion_rate, "rev": float(revenue), "events": event_count,
        },
    )

    # 다음 태스크(report)로 값 전달
    context["ti"].xcom_push(key="metrics", value={
        "date": ds, "dau": dau, "view_count": view_count,
        "purchase_count": purchase_count, "conversion_rate": round(conversion_rate, 4),
        "revenue": float(revenue), "event_count": event_count,
    })


def report(**context):
    """계산 결과를 로그로 출력."""
    metrics = context["ti"].xcom_pull(key="metrics", task_ids="compute_metrics")
    print("===== 일별 지표 리포트 =====")
    print(f"날짜:          {metrics['date']}")
    print(f"DAU:           {metrics['dau']:,}")
    print(f"조회수:        {metrics['view_count']:,}")
    print(f"구매수:        {metrics['purchase_count']:,}")
    print(f"전환율:        {metrics['conversion_rate']:.2%}")
    print(f"매출:          {metrics['revenue']:,.2f}")
    print(f"총 이벤트:     {metrics['event_count']:,}")
    print("===========================")


with DAG(
    dag_id="daily_etl",
    description="raw_events 기반 일별 지표(DAU/전환율/매출) 집계",
    schedule="@daily",                       # 매일 1회
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,                            # 자동으로 과거를 소급 실행하진 않지만,
                                               # Airflow UI에서 특정 과거 날짜를 골라
                                               # 수동으로 재실행(backfill)하는 건 그대로
                                               # 가능하다 - 각 태스크가 이미 특정 날짜
                                               # (ds/execution_date) 기준으로 동작하고
                                               # 멱등적으로 짜여 있어서 안전하다.
    default_args=DEFAULT_ARGS,                # 재시도 3회, 5분 간격 (adrs/0010)
    on_failure_callback=notify_failure_slack, # 재시도 소진 시 Slack 알림
    tags=["projecte", "batch", "metrics"],
) as dag:

    t1 = PythonOperator(task_id="ensure_table", python_callable=ensure_table)
    t2 = PythonOperator(task_id="compute_metrics", python_callable=compute_metrics)
    t3 = PythonOperator(task_id="report", python_callable=report)

    # 실행 순서: 테이블 보장 → 지표 계산 → 리포트
    t1 >> t2 >> t3