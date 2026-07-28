"""
앱 전역 설정.

로컬 실행: backend/.env 파일에서 값을 읽는다 (.env.example 참고).
Docker 실행: docker-compose.yml 의 environment 로 주입된 값을 그대로 읽는다.
             (.env 파일이 없어도 pydantic-settings 가 환경변수를 그대로 사용하므로 문제없다)
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PostgreSQL 접속 정보
    # 예: postgresql+psycopg2://user:password@localhost:5432/projecte
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/projecte"

    # React 개발 서버 CORS 허용 origin
    frontend_origin: str = "http://localhost:5173"

    # 환경 구분 (local / docker / production)
    env: str = "local"

    # --- Kafka 설정 ---
    # 로컬에서 FastAPI를 실행하므로 localhost:9092 (docker-compose의 PLAINTEXT_HOST)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_events_topic: str = "user-events"

    # 이벤트를 Kafka로 보낼지 여부.
    # False로 두면 (Kafka가 아직 없거나 끌 때) PostgreSQL에 직접 저장하는
    # 예전 방식으로 폴백한다. 개발/디버깅 편의를 위한 스위치.
    use_kafka: bool = True


settings = Settings()