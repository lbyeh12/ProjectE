"""
FastAPI 앱 엔트리포인트.

실행:
    uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import engine  # noqa: F401  (다른 모듈이 import 하는 경우가 있어 유지)
from app.routers import auth, cart, events, products
from app import kafka_producer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시: Kafka Producer 초기화 (use_kafka=True인 경우)
    kafka_producer.init_producer()
    yield
    # 앱 종료 시: 남은 메시지 flush 후 Producer 종료
    kafka_producer.close_producer()


app = FastAPI(title="ProjectE API", version="0.1.0", lifespan=lifespan)

# 테이블 생성/변경은 Alembic이 전담한다 (Base.metadata.create_all 은 더 이상 쓰지 않음).
# 로컬 실행: alembic upgrade head 를 uvicorn 실행 전에 한 번 실행.
# Docker 실행: backend/entrypoint.sh 가 컨테이너 시작 시 자동으로 실행.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(events.router)

# 요청 수 / 응답시간(p50·p95·p99) / 에러율을 /metrics 로 노출한다.
# Prometheus가 이 엔드포인트를 주기적으로 스크랩해간다 (adrs/0001 참고).
Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health_check():
    return {"status": "ok", "env": settings.env}