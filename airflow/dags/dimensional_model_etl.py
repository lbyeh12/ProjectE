"""
dimensional_model_etl DAG (adrs/0008-dimensional-modeling.md, adrs/0013-dbt-adoption.md)

raw_events 를 Star Schema(dim_date/dim_product/dim_user + fact_events)로
변환한다. 변환 로직(SCD2 갱신, fact 적재)은 더 이상 이 파일 안의 Python/
raw SQL이 아니라 dbt 모델(dbt/models/marts/*.sql)이 담당한다. 이 DAG은
dbt를 실행만 시키는 얇은 오케스트레이터다 (adrs/0013).

daily_etl(단순 집계)과 별도 DAG으로 분리한 이유: 이 DAG은 분석/BI
용도의 스키마를 소유하고, daily_etl은 운영 대시보드용 집계를 소유한다
- 서로 목적이 다른 결과물이라 독립적으로 재실행/실패해도 되게 분리했다.

이 DAG이 다루는 테이블은 FastAPI 애플리케이션의 SQLAlchemy 모델
(app/models.py, OLTP 스키마)과 별개다. 분석용 스키마(DW 레이어)는
dbt(이 DAG이 실행만 시킴)가 소유하고, 애플리케이션 스키마는 Alembic이
소유하는 것으로 책임을 나눴다.

파이프라인 단계:
  1. dbt_run  : dbt/models/marts 의 모든 모델 실행
               (dim_date -> dim_product/dim_user -> fact_events 순서는
               모델 파일의 ref() 의존성을 보고 dbt가 자동으로 정한다 -
               예전처럼 Airflow에서 사람이 t1 >> [t2,t3] >> t4 로 순서를
               직접 관리할 필요가 없어졌다)
  2. dbt_test : schema.yml에 정의된 unique/not_null/accepted_range 등
               검증 실행
  3. trigger_export_to_s3 : export_to_s3 DAG을 자동으로 실행

data_quality_check DAG이 끝나면 이 DAG을 TriggerDagRunOperator로 자동
실행시킨다(그 DAG 파일 참고). ExternalTaskSensor 대신 체인 방식을 쓰는
이유는 이전 버전의 docstring/perf 013 참고.
"""
from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from dag_common import DEFAULT_ARGS, notify_failure_slack

# dbt 프로젝트는 backend/scripts 처럼 별도 볼륨으로 마운트된다
# (docker-compose.yml 참고). dbt는 Airflow의 파이썬 환경과 의존성
# 충돌을 피하려고 별도 가상환경(/home/airflow/dbt-venv)에 설치했으므로
# (airflow/Dockerfile 참고), PATH의 "dbt"가 아니라 그 venv 안의
# 바이너리를 직접 호출한다.
DBT_PROJECT_DIR = "/opt/dbt"
DBT_BIN = "/home/airflow/dbt-venv/bin/dbt"

# 바인드 마운트된 /opt/dbt 안에 dbt가 target/logs/dbt_packages를 쓰려고
# 하면 권한 문제가 생길 수 있어(venv를 /opt 밖에 둔 것과 같은 이유),
# 컨테이너 로컬 경로로 지정한다. dbt_project.yml에는 안 넣고 명령 앞에
# 인라인으로 지정하는 이유는 dbt/dbt_project.yml 참고. BashOperator의
# env= 파라미터 대신 인라인 방식을 쓰는 이유: env=는 프로세스 환경을
# 통째로 교체할 수 있어서, docker-compose에서 설정한 DBT_DB_HOST 등
# (dbt profiles.yml이 필요로 하는 DB 접속 정보)이 사라질 위험이 있다.
# 인라인으로 붙이면 기존 환경을 그대로 물려받으면서 이 값들만 추가된다.
DBT_ENV_PREFIX = (
    "DBT_TARGET_PATH=/home/airflow/dbt-target "
    "DBT_LOG_PATH=/home/airflow/dbt-logs "
    "DBT_PACKAGES_INSTALL_PATH=/home/airflow/dbt-target/dbt_packages"
)

with DAG(
    dag_id="dimensional_model_etl",
    description="raw_events -> Star Schema(dim_date/product/user, fact_events) 변환 (dbt)",
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    on_failure_callback=notify_failure_slack,
    tags=["projecte", "batch", "dimensional-model", "dbt"],
) as dag:

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_ENV_PREFIX} {DBT_BIN} deps --profiles-dir .",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_ENV_PREFIX} {DBT_BIN} run --profiles-dir .",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_ENV_PREFIX} {DBT_BIN} test --profiles-dir .",
    )

    # 이 DAG이 끝나면 export_to_s3를 자동으로 실행시킨다.
    trigger_next = TriggerDagRunOperator(
        task_id="trigger_export_to_s3",
        trigger_dag_id="export_to_s3",
        logical_date="{{ logical_date }}",
        wait_for_completion=False,
        # 백필 시 이미 같은 logical_date의 실행이 있으면 에러 대신
        # 리셋하고 재트리거 (data_quality_check.py와 동일한 이유).
        reset_dag_run=True,
    )

    dbt_deps >> dbt_run >> dbt_test >> trigger_next