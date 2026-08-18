"""
data_quality_check DAG (adrs/0009-data-quality-validation.md)

raw_events 를 검증해서 불량 데이터를 quarantine_events 로 격리한다.
raw_events 원본은 건드리지 않는다 - "원본 로그는 손대지 않는다"는
원칙을 지키기 위해서다(감사/디버깅 목적으로 항상 원본을 보존).
대신 다운스트림(dimensional_model_etl, daily_etl)이 격리된
source_event_id 를 걸러내고 읽도록 한다.

검증 규칙은 Great Expectations(1.x, Fluent/Core API)로 선언하고
위반 건수를 로그로 리포트한다. GE는 "규칙 선언 + 리포트" 역할만
맡고, "정확히 어느 행을 격리할지"는 pandas 불리언 마스크가 별도로
판정한다 - GE 호출은 try/except로 감싸 API 버전 차이 등으로
실패해도 격리 로직에는 영향이 없게 한다 (docs/perf/012 참고).

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
    # ExternalTaskSensor(logical_date 일치 요구) 대신 체인 방식을 쓴
    # 이유는 docs/perf/013-dag-dependency-chain.md 참고.
    trigger_next = TriggerDagRunOperator(
        task_id="trigger_dimensional_model_etl",
        trigger_dag_id="dimensional_model_etl",
        logical_date="{{ logical_date }}",  # 같은 논리 날짜를 그대로 전달
        wait_for_completion=False,  # "실행시키기"만 하고 바로 끝남 (fire-and-forget)
    )

    t1 >> t2 >> trigger_next