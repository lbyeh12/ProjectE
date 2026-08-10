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

    # --- JWT 인증 설정 ---
    # 운영 배포 시에는 반드시 .env / 환경변수로 강력한 랜덤 값을 주입해야 한다.
    # (이 기본값은 로컬 개발 편의용이며 저장소에 그대로 커밋되어 있으므로 안전하지 않다)
    jwt_secret_key: str = "dev-only-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24시간

    # --- DB 커넥션 풀 설정 ---
    # SQLAlchemy 기본값(pool_size=5, max_overflow=10, 최대 15개)이 대규모
    # 트래픽에서 병목이었음을 부하 테스트로 확인함 (docs/perf/002-stress-test.md).
    # 값을 늘려서 재검증한다. PostgreSQL 자체의 max_connections(기본 100)도
    # 함께 고려해야 한다 (다른 서비스: Airflow 등도 같은 PostgreSQL을 공유).
    db_pool_size: int = 20
    db_max_overflow: int = 30

    # --- Redis 설정 (멱등성 키 저장소, adrs/0006) ---
    redis_url: str = "redis://localhost:6379/0"
    # 멱등성 키 보관 기간(초). "사용자가 재시도할 만한 시간"이면
    # 충분하다고 보고 10분으로 잡는다.
    idempotency_ttl_seconds: int = 600


settings = Settings()