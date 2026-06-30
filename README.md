# 실시간 사용자 행동 데이터 플랫폼

전자상거래 웹 서비스를 직접 구축하고, 그 위에서 발생하는 사용자 행동 데이터를 실시간으로 수집·처리·분석하는 데이터 플랫폼 프로젝트입니다. React/FastAPI로 만든 서비스에서 발생한 이벤트가 Kafka → Spark Streaming → PostgreSQL을 거쳐 실시간 대시보드에 반영되고, Airflow가 매일 배치로 DAU/MAU/Conversion Rate 같은 지표를 집계합니다.

---

## 1. 아키텍처

```
사용자
  │
  ▼
React (Frontend)
  │
  ▼
FastAPI (Backend)
  │
  ▼
Kafka Producer
  │
  ▼
Kafka (KRaft 모드)
  │
  ▼
Spark Streaming (Consumer)
  │
  ▼
PostgreSQL
  ├── Airflow Batch ETL  → DAU / MAU / Conversion Rate / Retention
  │
  └── Dashboard (Streamlit / Superset)

전체 서비스
  │
  ▼
Docker (개발) → Kubernetes (운영)
  │
  ▼
Prometheus + Grafana (모니터링)
```

---

## 2. 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React, TypeScript, Vite, React Router, TanStack Query, Zustand, Tailwind CSS |
| Backend | FastAPI |
| Message Queue | Apache Kafka (KRaft 모드, Zookeeper 미사용) |
| Data Processing | Apache Spark, Spark Streaming |
| Workflow | Apache Airflow |
| Database | PostgreSQL |
| Dashboard | Streamlit, Apache Superset |
| Container / Orchestration | Docker, Docker Compose, Kubernetes |
| Monitoring | Prometheus, Grafana |

---

## 3. 데이터셋

UCI **Online Retail** 데이터셋(`ecommerce_data.csv`)을 기반으로 합니다.

- 원본은 약 54만 건의 거래 라인(2010-12 ~ 2011-12, 영국 온라인 쇼핑몰)이며 `InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country` 컬럼으로 구성되어 있습니다.
- **이 데이터셋에는 view/search/cart 같은 행동 로그가 없고, 완료된 거래 기록만 존재합니다.** 따라서 `scripts/preprocess.py`에서 거래 기록을 기반으로 view → add_to_cart → purchase 퍼널을 합성해서 행동 이벤트를 만들어냅니다 (비율 view:cart:purchase ≈ 10:3:1).
- 원본 CSV와 전처리로 생성되는 파일들은 저장소에 포함하지 않습니다 (`.gitignore` 참고). 재생성 방법은 아래 "데이터 준비" 섹션을 참고하세요.

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

---

## 4. 폴더 구조

```
project/
├── frontend/              # React 웹 서비스
├── backend/                # FastAPI (상품/장바구니/주문/이벤트 API, Kafka Producer)
├── data/
│   ├── preprocess.py        # 원본 CSV 전처리 + 행동 이벤트 합성
│   └── dataset/
│       └── *.csv 
├── scripts/
│   └── simulator.py         # 이벤트를 FastAPI로 실시간 전송하는 시뮬레이터
├── spark/                   # Spark Streaming 잡 (Kafka Consumer → 실시간 집계)
├── airflow/                  # 배치 ETL DAG (daily_etl)
├── dashboard/                # Streamlit 대시보드
├── k8s/                       # Kubernetes manifest
├── requirements-app.txt        # 전처리/시뮬레이터/백엔드용 패키지
├── requirements-spark.txt       # Spark Streaming용 패키지
├── requirements-airflow.txt      # Airflow용 패키지 (별도 가상환경 필수)
├── requirements-dashboard.txt     # Streamlit 대시보드용 패키지
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 5. 개발 환경 준비

가상환경은 컴포넌트별로 분리해서 사용합니다 (특히 Airflow는 의존성이 엄격하게 고정되어 있어 다른 패키지와 같은 환경에 두면 충돌이 발생합니다).

### 5-1. 앱 환경 (전처리 / 시뮬레이터 / FastAPI)

```bash
python3 -m venv venv-app
source venv-app/bin/activate      # Windows: venv-app\Scripts\activate
pip install -r requirements-app.txt
```

### 5-2. Spark 환경

```bash
python3 -m venv venv-spark
source venv-spark/bin/activate
pip install -r requirements-spark.txt
```

> PySpark는 로컬에 Java(JVM)가 설치되어 있어야 동작합니다. Kafka 연동 시에는 `spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:<spark버전>` 옵션으로 Kafka 커넥터 jar를 함께 받아야 합니다.

### 5-3. Airflow 환경

```bash
python3 -m venv venv-airflow
source venv-airflow/bin/activate

AIRFLOW_VERSION=2.9.3
PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
pip install "apache-airflow[postgres]==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"
```

### 5-4. 대시보드 환경

```bash
pip install -r requirements-dashboard.txt   # venv-app에 같이 설치해도 무방
```

---

## 6. 데이터 준비 (전처리 실행)

원본 CSV(`ecommerce_data.csv`)는 저장소에 포함되어 있지 않으므로, 직접 준비한 뒤 아래 스크립트로 가공합니다.

```bash
source venv-app/bin/activate
python scripts/preprocess.py \
  --input ecommerce_data.csv \
  --outdir ./data \
  --sample 1.0
```

빠른 개발/테스트 시에는 `--sample 0.1` 옵션으로 10%만 처리할 수 있습니다.

생성되는 파일:

| 파일 | 내용 |
|---|---|
| `products.csv` | 상품 카탈로그 (상품ID, 상품명, 가격) |
| `users.csv` | 회원 사용자 목록 |
| `purchases.csv` | 정제된 구매 거래 |
| `refunds.csv` | 환불/취소 거래 |
| `events.csv` | view / add_to_cart / purchase / refund 합성 이벤트 로그 |

---


## 8. 라이선스 및 데이터 출처

데이터셋은 UCI Machine Learning Repository의 Online Retail 데이터셋을 가공하여 사용합니다. 이 저장소에는 원본 데이터가 포함되어 있지 않습니다.
