# Airflow 커스텀 이미지
# 공식 이미지에 이 프로젝트 DAG이 필요로 하는 provider를 추가 설치한다.
FROM apache/airflow:3.3.0

# PostgresHook 사용을 위한 provider
# (pip install은 airflow 사용자 권한으로 실행해야 함)
RUN pip install --no-cache-dir apache-airflow-providers-postgres

# 데이터 품질 검증 (adrs/0009-data-quality-validation.md).
# 처음엔 0.18.x(구버전, numpy 1.26 요구)로 고정했다가 빌드가 실패했다 -
# 이 이미지에 이미 numpy 2.5.0/pandas 2.3.3이 있는데, 0.18.x가 그보다
# 훨씬 오래된 numpy로 다운그레이드를 시도하면서 소스 컴파일로 넘어가고,
# Airflow 이미지는 비root 사용자라 컴파일러 실행 권한이 없어 실패했다.
# 최신 1.x대(numpy 2.x 호환 버그 수정이 이미 반영됨)로 바꿔서 해결한다.
# pandas는 이미 설치되어 있으므로 별도로 다시 설치하지 않는다.
RUN pip install --no-cache-dir "great_expectations==1.20.0"

# 파이프라인 안정성 (adrs/0010-airflow-pipeline-reliability.md).
# Slack 알림에 필요. Airflow 코어가 내부적으로 requests에 의존하는
# 경우가 많아 이미 있을 가능성이 높지만, GE 버전 사태로 "가정하지
# 말고 명시적으로 설치"하기로 했으므로 여기 명시한다.
RUN pip install --no-cache-dir requests

# AWS 클라우드 연동 (adrs/0011-aws-data-lake-integration.md).
# apache-airflow-providers-amazon 은 boto3를 함께 설치하고 S3Hook 등을
# 제공한다 - PostgresHook을 쓸 때처럼, raw boto3 호출보다 Airflow의
# provider/hook 계층을 통해 일관되게 다룬다. pyarrow는 pandas가
# Parquet 파일을 쓰기 위해 필요하다.
RUN pip install --no-cache-dir apache-airflow-providers-amazon pyarrow

# dbt (adrs/0013-dbt-adoption.md).
# dbt-core는 Jinja2 등 의존성 버전을 Airflow 자체와 다르게 요구하는
# 경우가 실무에서 흔히 보고된다 - 이미 GE 버전 충돌(numpy)을 겪었던
#것과 같은 종류의 위험이다. Airflow의 파이썬 환경과 아예 공유하지
# 않도록 별도 가상환경에 설치해서, 충돌 가능성 자체를 원천 차단한다.
# DAG에서는 dbt를 PATH의 "dbt"가 아니라 이 venv 경로로 직접 호출한다.
#
# 경로를 /opt가 아니라 /home/airflow(컨테이너의 airflow 사용자 홈)
# 밑에 두는 이유: /opt는 root 소유라 비root 사용자(이 이미지가
# pip install을 실행하는 airflow 사용자)가 새 폴더를 만들 권한이
# 없어 "Permission denied"로 빌드가 실패했다. 홈 디렉토리는 그
# 사용자가 항상 쓰기 권한을 갖는 경로라 이 문제가 없다.
# RUN python -m venv /home/airflow/dbt-venv && \
# dbt-postgres만 버전을 고정했더니, pip가 dbt-core는 훨씬 최신인
# 2.0.0-beta.1을 끌어와서(dbt-postgres의 내부 의존성 제약이 dbt-core
# 상한을 안 걸어둔 것으로 보임) dbt_project.yml의 log-path 설정이
# "dbt1005: 'log-path' cannot be specified" 에러로 실패했다.
# (2.0 베타에서 설정 스펙이 바뀐 것으로 보인다.) dbt-core도 같이
# 명시적으로 고정해서, pip가 절대 1.9 이상을 고르지 못하게 한다.
RUN python -m venv /home/airflow/dbt-venv && \
    /home/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core>=1.8,<1.9" "dbt-postgres>=1.8,<1.9"