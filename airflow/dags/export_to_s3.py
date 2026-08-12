"""
export_to_s3 DAG (adrs/0011-aws-data-lake-integration.md)

raw_events, fact_events 를 그 날짜 분량만큼 Parquet으로 변환해서
S3에 올린다. 새 컴포넌트(별도 ETL 도구) 없이 Airflow 태스크로 직접
처리한다.

경로 구조 (Hive 스타일 파티셔닝, Glue Crawler가 자동으로 dt를
파티션 컬럼으로 인식):
  s3://{bucket}/raw/raw_events/dt=YYYY-MM-DD/part-0000.parquet
  s3://{bucket}/curated/fact_events/dt=YYYY-MM-DD/part-0000.parquet

raw/ 에는 raw_events를 가공 없이 그대로 내보낸다 - 변환은 이미
dimensional_model_etl이 로컬 DB에서 끝냈지만, "원본은 원본대로,
가공본은 가공본대로" 두는 ELT적 구조를 클라우드 쪽에서도 그대로
보여주기 위해 raw 경로는 비가공 상태로 유지한다. curated/ 에는
이미 변환된 fact_events를 내보낸다.

이 DAG은 dimensional_model_etl이 끝나면 TriggerDagRunOperator로
자동 실행된다 (그 DAG 파일 참고) - ExternalTaskSensor로 두 DAG의
logical_date가 정확히 일치해야만 연결되는 방식은, 수동으로 각 DAG을
서로 다른 시각에 트리거하면 영원히 대기하는 문제가 있어서 이 체인
방식으로 바꿨다. 이 DAG 자체를 단독으로 수동 실행해도 문제없이
동작한다.

AWS 자격증명이 없으면(AWS_ACCESS_KEY_ID 등 미설정) 이 DAG의 태스크는
명확한 에러로 실패한다. 이 프로젝트의 나머지 부분(로컬 파이프라인
전체)은 AWS 없이도 완전히 동작하므로, AWS 계정이 없다면 이 DAG만
비활성 상태로 둬도 무방하다.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook

from dag_common import DEFAULT_ARGS, notify_failure_slack

PG_CONN_ID = "projecte_db"
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "projecte-data-lake")


def _upload_df_as_parquet(df: pd.DataFrame, s3_key: str) -> None:
    """
    DataFrame을 Parquet으로 직렬화해서 S3에 올린다. 로컬에 임시
    파일을 안 거치고 메모리(BytesIO)에서 바로 업로드한다.

    같은 키로 재시도해도 replace=True 라 덮어쓰기만 일어나고 중복
    파일이 쌓이지 않는다 (adrs/0010의 멱등성 원칙과 동일하게 적용).
    """
    if df.empty:
        print(f"[export_to_s3] {s3_key}: 대상 데이터 없음, 스킵")
        return

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    # aws_conn_id=None: Airflow Connection을 따로 등록하지 않고, boto3의
    # 기본 자격증명 탐색(환경변수 AWS_ACCESS_KEY_ID 등)을 그대로 쓴다.
    # PostgresHook처럼 Airflow Connection으로 관리하는 대신 이 방식을
    # 택한 이유: docker-compose 환경변수 하나로 로컬 개발/CI 양쪽에서
    # 동일하게 다루기가 더 간단하다.
    hook = S3Hook(aws_conn_id=None)
    hook.load_bytes(
        bytes_data=buffer.read(),
        key=s3_key,
        bucket_name=S3_BUCKET,
        replace=True,
    )
    print(f"[export_to_s3] {len(df)}건 -> s3://{S3_BUCKET}/{s3_key}")


def export_raw_events_to_s3(**context):
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=PG_CONN_ID)
    df = hook.get_pandas_df(
        "SELECT * FROM raw_events WHERE timestamp::date = %(ds)s",
        parameters={"ds": ds},
    )
    _upload_df_as_parquet(df, f"raw/raw_events/dt={ds}/part-0000.parquet")


def export_fact_events_to_s3(**context):
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=PG_CONN_ID)
    # dimensional_model_etl 이 date_key를 TO_CHAR(..., 'YYYYMMDD')::int
    # 로 만들었던 것과 동일한 형식으로 맞춰서 조회한다.
    date_key = int(ds.replace("-", ""))
    df = hook.get_pandas_df(
        "SELECT * FROM fact_events WHERE date_key = %(date_key)s",
        parameters={"date_key": date_key},
    )
    _upload_df_as_parquet(df, f"curated/fact_events/dt={ds}/part-0000.parquet")


with DAG(
    dag_id="export_to_s3",
    description="raw_events/fact_events 를 Parquet으로 S3(데이터 레이크)에 적재",
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    on_failure_callback=notify_failure_slack,
    tags=["projecte", "batch", "aws"],
) as dag:

    # dimensional_model_etl이 끝나면 이 DAG이 트리거되어 실행되므로,
    # 여기서는 별도 대기 없이 바로 시작한다. t1, t2는 서로 독립적이라
    # 병렬로 실행한다.
    t1 = PythonOperator(task_id="export_raw_events_to_s3", python_callable=export_raw_events_to_s3)
    t2 = PythonOperator(task_id="export_fact_events_to_s3", python_callable=export_fact_events_to_s3)