#!/bin/bash
# backend/entrypoint.sh
#
# 컨테이너가 뜰 때마다 먼저 DB 스키마를 최신 상태로 맞추고(alembic upgrade head),
# 그다음 실제 서버(uvicorn)를 실행한다.
# 이렇게 해두면 "코드는 배포됐는데 마이그레이션을 깜빡해서 컬럼이 없다"는
# 사고(우리가 hashed_password 추가할 때 겪었던 문제)가 구조적으로 방지된다.
set -e

echo "[entrypoint] 데이터베이스 마이그레이션 적용 중..."
alembic upgrade head

echo "[entrypoint] 서버 시작"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
