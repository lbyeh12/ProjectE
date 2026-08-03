# backend/Dockerfile
# FastAPI 백엔드 (개발용: uvicorn --reload 로 코드 변경 시 자동 재시작)
FROM python:3.12-slim

WORKDIR /app

# 시스템 패키지 (psycopg2 빌드에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# requirements 는 backend 상위(프로젝트 루트)에 있으므로 build context를 루트로 잡고 복사한다.
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

# 코드는 볼륨 마운트로 제공되므로 COPY는 생략 (docker-compose volumes 참고)
# 단, entrypoint.sh 는 볼륨 마운트로도 덮어써지므로 실행권한만 별도로 부여해둔다.
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]