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

# uvicorn 의 --reload 와 --workers 는 동시에 쓸 수 없다 (--reload 는
# 단일 프로세스가 전제). 평소 개발 중에는 코드 수정이 즉시 반영되는
# --reload 가 편하지만, 부하 테스트/운영 검증 시에는 워커를 여러 개
# 띄워야 한다 (VU 750 스트레스 테스트에서 워커 1개가 처리 못 하고
# 요청이 계속 밀리는 것을 확인함 - docs/perf/002-stress-test.md).
#
# WORKERS 환경변수로 전환한다.
#   WORKERS 미설정 또는 1 -> 기존처럼 --reload 로 개발 모드 실행
#   WORKERS 2 이상        -> --reload 없이 --workers N 으로 실행
WORKERS="${WORKERS:-1}"

if [ "$WORKERS" -le 1 ]; then
  echo "[entrypoint] 개발 모드로 서버 시작 (--reload, 워커 1개)"
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  echo "[entrypoint] 서버 시작 (--workers ${WORKERS}, reload 비활성)"
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
fi