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