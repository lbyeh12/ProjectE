# Airflow 커스텀 이미지
# 공식 이미지에 이 프로젝트 DAG이 필요로 하는 provider를 추가 설치한다.
FROM apache/airflow:3.3.0

# PostgresHook 사용을 위한 provider
# (pip install은 airflow 사용자 권한으로 실행해야 함)
RUN pip install --no-cache-dir apache-airflow-providers-postgres
