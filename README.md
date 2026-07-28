# 실시간 사용자 행동 데이터 플랫폼

전자상거래 웹 서비스를 직접 구축하고, 그 위에서 발생하는 사용자 행동 데이터를 실시간으로 수집·처리·분석하는 데이터 플랫폼 프로젝트입니다. React/FastAPI로 만든 서비스에서 발생한 이벤트가 Kafka → Spark Streaming을 거쳐 PostgreSQL에 실시간 집계되고, Airflow가 매일 배치로 DAU/전환율/매출 같은 지표를 집계합니다. 두 결과 모두 Streamlit 대시보드에서 확인할 수 있습니다.

---

## 1. 아키텍처

```
[실시간 경로]
사용자 / 시뮬레이터
   │
   ▼
React (Frontend)  ──POST /events──▶  FastAPI (Backend)
                                          │
                                          ▼
                                   Kafka (KRaft 모드, user-events 토픽)
                                          │
                                          ▼
                                   Spark Streaming (로컬 실행)
                                          │
                                          ▼
                                     PostgreSQL
                              ├── raw_events (원본 이벤트)
                              ├── product_stats (실시간 인기 상품)
                              └── traffic_stats (분당 트래픽)

[배치 경로]
PostgreSQL(raw_events) ──▶ Airflow (daily_etl DAG, 매일 1회) ──▶ daily_metrics
                                                                (DAU / 전환율 / 매출)

[시각화]
PostgreSQL ──▶ Streamlit 대시보드 (실시간 탭 + 배치 탭)

[인프라]
Docker Compose: postgres, kafka, kafka-ui, airflow(4개 컨테이너),
                backend, frontend, dashboard
Spark만 로컬에서 별도 실행 (Java 의존성 때문에 컨테이너화 제외)
```

---

## 2. 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React, TypeScript, Vite, React Router, TanStack Query, Zustand, Axios |
| Backend | FastAPI, SQLAlchemy, kafka-python |
| Message Queue | Apache Kafka (KRaft 모드, Zookeeper 미사용) |
| Data Processing | Apache Spark 4.x (Structured Streaming) |
| Workflow | Apache Airflow 3.x (LocalExecutor) |
| Database | PostgreSQL 16 |
| Dashboard | Streamlit |
| Container | Docker, Docker Compose |
| Orchestration (예정) | Kubernetes |
| Monitoring (예정) | Prometheus, Grafana |

---

## 3. 데이터셋

UCI **Online Retail** 데이터셋(`ecommerce_data.csv`)을 기반으로 합니다.

- 원본은 약 54만 건의 거래 라인(2010-12 ~ 2011-12, 영국 온라인 쇼핑몰)이며 `InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country` 컬럼으로 구성되어 있습니다.
- **이 데이터셋에는 view/search/cart 같은 행동 로그가 없고, 완료된 거래 기록만 존재합니다.** 따라서 `data/preprocess.py`에서 거래 기록을 기반으로 view → add_to_cart → purchase 퍼널을 합성해서 행동 이벤트를 만들어냅니다 (비율 view:cart:purchase ≈ 10:3:1).
- 원본 CSV와 전처리로 생성되는 파일들은 저장소에 포함하지 않습니다 (`.gitignore` 참고).

### 이벤트 스키마 (확정)

```json
{
  "user_id": 17850,
  "event_type": "view",
  "product_id": "85123A",
  "price": 2.55,
  "timestamp": "2026-06-19T12:00:00"
}
```

`event_type`: `view`, `search`, `add_to_cart`, `purchase`, `refund`, `signup`, `login`

모든 사용자 행동은 프론트엔드의 `trackEvent()` 함수 하나만 거쳐 `POST /events`로 전송됩니다. 백엔드는 이 이벤트를 Kafka로 전송하며(`use_kafka=False`일 때만 DB 직접 저장으로 폴백), 프론트엔드는 이 내부 구현과 무관하게 항상 동일한 인터페이스로 이벤트를 보냅니다.

---

## 4. 폴더 구조

```
project/
├── frontend/                  # React 웹 서비스
│   ├── Dockerfile
│   └── src/
├── backend/                    # FastAPI (상품/장바구니/이벤트/구매 API, Kafka Producer)
│   ├── Dockerfile
│   ├── app/
│   └── scripts/load_data.py     # products/users CSV → DB 적재
├── data/
│   ├── preprocess.py              # 원본 CSV 전처리 + 행동 이벤트 합성
│   └── dataset/                    # 원본 CSV + 전처리 결과물 (미포함, .gitignore)
├── scripts/
│   ├── simulator.py                 # 합성 이벤트를 FastAPI로 실시간 전송
│   └── kafka_setup.py                # Kafka 토픽 생성/확인
├── spark/                              # Spark Streaming (로컬 실행)
│   ├── streaming_job.py
│   ├── run_streaming.sh                 # Java 17 자동 감지 + spark-submit
│   ├── reset_checkpoints.sh              # Kafka 리셋 후 체크포인트 초기화
│   └── schema.sql                         # product_stats/traffic_stats 테이블 정의
├── airflow/
│   ├── Dockerfile
│   ├── dags/daily_etl.py                  # 일별 DAU/전환율/매출 집계 DAG
│   ├── init-airflow-db.sql                 # airflow 메타데이터 DB 자동 생성
│   └── simple_auth_manager_passwords.json   # 로그인 비밀번호 고정 (미포함, .gitignore)
├── dashboard/                                # Streamlit 대시보드 (실시간 + 배치)
│   ├── Dockerfile
│   ├── app.py
│   └── db.py
├── requirements-app.txt         # 전처리/시뮬레이터/백엔드용 패키지
├── requirements-spark.txt        # Spark용 패키지 (로컬 venv)
├── requirements-dashboard.txt     # 대시보드용 패키지
├── docker-compose.yml               # 인프라 + Airflow + 애플리케이션 전체
├── .gitignore
└── README.md
```

---

## 5. 실행 방법

### 5-1. 사전 준비

- Docker Desktop
- Python 3.9+ (venv-app, venv-spark 용)
- Java 17 (Spark 로컬 실행용, 없으면 `brew install openjdk@17`)
- Node.js (React 로컬 실행 시에만 필요. Docker로 띄우면 불필요)

### 5-2. 가상환경

Spark는 Java/버전 의존성이 까다로워 별도 가상환경을 씁니다. Airflow는 Docker 컨테이너로 실행하므로 로컬 가상환경이 필요 없습니다.

```bash
# 앱 환경 (전처리 / 시뮬레이터 / 백엔드는 Docker로도 실행되지만 로컬 스크립트 실행용으로 필요)
python3 -m venv venv-app
source venv-app/bin/activate
pip install -r requirements-app.txt

# Spark 환경
python3 -m venv venv-spark
source venv-spark/bin/activate
pip install -r requirements-spark.txt
```

### 5-3. 데이터 준비 (전처리)

원본 CSV(`ecommerce_data.csv`)를 `data/dataset/`에 받아둔 뒤 실행합니다.

```bash
source venv-app/bin/activate
python data/preprocess.py \
  --input data/dataset/ecommerce_data.csv \
  --outdir data/dataset \
  --sample 1.0
```

`--sample 0.1`로 10%만 빠르게 처리할 수도 있습니다. 생성 파일: `products.csv`, `users.csv`, `purchases.csv`, `refunds.csv`, `events.csv`.

### 5-4. 전체 서비스 실행 (Docker Compose)

인프라(PostgreSQL, Kafka, Airflow)와 애플리케이션(backend, frontend, dashboard)을 한 번에 띄웁니다.

```bash
docker compose up -d --build
docker compose ps               # 전부 healthy/running 인지 확인
```

| 서비스 | 포트 | 용도 |
|---|---|---|
| PostgreSQL | 5432 | 이벤트/집계 데이터 저장 |
| Kafka | 9092 | 로컬(FastAPI/시뮬레이터)에서 접속 |
| Kafka UI | 8080 | 토픽/메시지 확인 (http://localhost:8080) |
| Airflow UI | 8081 | 배치 DAG 관리 (http://localhost:8081, 계정은 `airflow/simple_auth_manager_passwords.json` 참고) |
| Backend (FastAPI) | 8000 | REST API (http://localhost:8000/docs) |
| Frontend (React) | 5173 | 웹 서비스 (http://localhost:5173) |
| Dashboard (Streamlit) | 8501 | 대시보드 (http://localhost:8501) |

backend/frontend/dashboard는 코드 폴더를 볼륨 마운트하므로, 코드 수정 시 컨테이너 재빌드 없이 자동 반영됩니다(hot reload).

```bash
docker compose logs -f backend   # 특정 서비스 로그
docker compose down              # 중지 (데이터 유지)
docker compose down -v           # 중지 + 볼륨 삭제 (DB/Kafka 데이터 초기화)
```

> **`down -v` 이후 주의**: Kafka 토픽이 초기화되므로, Spark를 재실행하기 전에 `bash spark/reset_checkpoints.sh`로 체크포인트를 지워야 offset 불일치 에러가 나지 않습니다.

DB에 상품/유저 데이터 적재 (최초 1회):

```bash
docker exec projecte-backend python scripts/load_data.py --dataset-dir ../data/dataset
```

Kafka 토픽을 미리 만들려면 (선택, 자동 생성도 됨):

```bash
python scripts/kafka_setup.py
```

### 5-5. Spark Streaming 실행 (로컬)

Spark는 Java/리소스 설정이 까다로워 컨테이너화하지 않고 로컬에서 직접 실행합니다.

```bash
source venv-spark/bin/activate
bash spark/run_streaming.sh
```

스크립트가 Java 17을 자동으로 찾아 사용합니다. Kafka 볼륨을 지운 뒤라면 먼저 `bash spark/reset_checkpoints.sh`를 실행하세요.

### 5-6. 이벤트 발생시키기

```bash
cd scripts

# 실제 데이터를 시간순으로 재생 (원본은 2011년 데이터)
python simulator.py replay --speed 60

# 또는 현재 시각 기준 무한 랜덤 이벤트 (대시보드/배치 테스트에 적합)
python simulator.py random --rate 10 --limit 1000
```

### 5-7. Airflow 배치 실행

`http://localhost:8081` 접속 → `daily_etl` DAG 활성화(토글) → 수동 실행(▶). raw_events를 집계해 `daily_metrics`에 저장합니다.

---

## 6. 대시보드

`http://localhost:8501`에서 두 개 탭을 제공합니다.

- **실시간**: 현재 접속자, 오늘 누적 매출, 실시간 인기 상품, 1분 단위 트래픽 (10초 자동 갱신)
- **배치**: 최근 DAU/전환율/매출, 일별 추이 차트 (Airflow `daily_etl` 결과)

---

## 7. 라이선스 및 데이터 출처

데이터셋은 UCI Machine Learning Repository의 Online Retail 데이터셋을 가공하여 사용합니다. 이 저장소에는 원본 데이터가 포함되어 있지 않습니다.