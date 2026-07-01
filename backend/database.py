"""
SQLAlchemy 엔진 / 세션 / Base 선언.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI 의존성(Depends)으로 사용할 DB 세션 제너레이터.
    요청 처리 후 항상 세션을 닫는다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
