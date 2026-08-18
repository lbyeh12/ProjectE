# Airflow 커스텀 이미지
# 공식 이미지에 이 프로젝트 DAG이 필요로 하는 provider를 추가 설치한다.
FROM apache/airflow:3.3.0

# PostgresHook 사용을 위한 provider
# (pip install은 airflow 사용자 권한으로 실행해야 함)
RUN pip install --no-cache-dir apache-airflow-providers-postgres

# 데이터 품질 검증 (adrs/0009-data-quality-validation.md).
# 1.x대로 고정: 이 이미지의 numpy/pandas와 호환된다.
RUN pip install --no-cache-dir "great_expectations==1.20.0"

# 파이프라인 안정성 (adrs/0010-airflow-pipeline-reliability.md). Slack 알림용.
RUN pip install --no-cache-dir requests

# AWS 클라우드 연동 (adrs/0011-aws-data-lake-integration.md).
# S3Hook 등 제공. pyarrow는 pandas의 Parquet 쓰기에 필요.
RUN pip install --no-cache-dir apache-airflow-providers-amazon pyarrow

# dbt (adrs/0013-dbt-adoption.md).
# dbt-core는 Airflow와 의존성 버전 요구가 달라 충돌할 수 있어, 별도
# 가상환경에 설치해 분리한다. DAG은 PATH의 "dbt"가 아니라 이 venv
# 경로로 직접 호출한다. /home/airflow(비root 사용자 홈) 밑에 두는 건
# /opt가 root 소유라 쓰기 권한이 없기 때문. dbt-core 버전도 함께
# 고정해서 dbt-postgres가 호환되지 않는 최신 버전을 끌어오지 않게 한다.
RUN python -m venv /home/airflow/dbt-venv && \
    /home/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core>=1.8,<1.9" "dbt-postgres>=1.8,<1.9"