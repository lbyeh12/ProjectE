"""
FastAPI 앱 엔트리포인트.

실행:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import cart, events, products

app = FastAPI(title="ProjectE API", version="0.1.0")

# 개발 단계에서는 Alembic 마이그레이션 대신 시작 시 테이블을 바로 생성한다.
# (운영 단계로 가면 Alembic으로 교체)
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(cart.router)
app.include_router(events.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "env": settings.env}
