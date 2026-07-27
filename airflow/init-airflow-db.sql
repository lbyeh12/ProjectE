-- Airflow 메타데이터 전용 데이터베이스 생성.
-- postgres 컨테이너가 처음 초기화될 때 1회 실행된다.
-- (애플리케이션 데이터는 projecte DB, Airflow 내부용은 airflow DB로 분리)
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
