"""
앱 전역 설정.
.env 파일에서 값을 읽어온다 (pydantic-settings 사용).
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


settings = Settings()
