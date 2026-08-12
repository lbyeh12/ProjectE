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