# frontend/Dockerfile
# React 개발 서버 (Vite). hot reload 를 위해 개발 서버를 그대로 컨테이너화한다.
# (운영 배포 시에는 멀티스테이지 빌드로 정적 파일을 만들어 nginx 등으로 서빙하는
#  별도 Dockerfile.prod 를 쓰는 것이 일반적이다.)
FROM node:20-slim

WORKDIR /app

# package.json 만 먼저 복사해서 의존성 캐시를 활용한다.
COPY package.json ./
RUN npm install

EXPOSE 5173

# --host 0.0.0.0 이 중요: 기본값(localhost)이면 컨테이너 밖에서 접속이 안 된다.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
