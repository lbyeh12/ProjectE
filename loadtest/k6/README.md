# k6 부하 테스트

대규모 트래픽 대응 전략(`adrs/0002-load-testing-strategy.md`)의
1단계: 부하를 실제로 걸어서 병목을 관찰하기 위한 스크립트 모음.

## 설치

```bash
brew install k6          # macOS
# 또는 https://k6.io/docs/get-started/installation/
```

## 사전 조건

- `docker compose up -d --build` 로 백엔드/DB/Kafka 등이 떠 있어야 함
- `python scripts/load_data.py` 로 상품/유저 데이터가 DB에 적재되어 있어야 함
  (browse 시나리오가 `GET /products` 결과를 씀)
- `data/dataset/users.csv` 가 존재해야 함 (purchase_flow 시나리오가 로그인
  계정을 준비할 때 읽음). 없으면 `python data/preprocess.py` 먼저 실행.

## 중요: 항상 프로젝트 루트에서, `-e PROJECT_ROOT=$(pwd)`와 함께 실행

`lib/setup.js`가 `users.csv`를 읽을 때 k6의 `open()`을 쓰는데, 이 함수가
상대경로를 해석하는 기준(현재 디렉토리 vs entry 스크립트 위치)이 k6
버전/실행 방식에 따라 달라질 수 있어서, 추측 대신 **환경변수로 절대경로를
직접 넘긴다.** 아래 예시처럼 모든 명령에 `-e PROJECT_ROOT=$(pwd)`를
반드시 포함해야 한다 (프로젝트 루트에서 실행한다는 전제).

## 구조

```
loadtest/k6/
├── lib/
│   ├── config.js       # BASE_URL, 테스트 비밀번호
│   └── setup.js         # 시작 시 1회: users.csv에서 계정 뽑아 회원가입
├── scenarios/
│   ├── browse.js         # 다수 트래픽: 비로그인 상품 조회/검색
│   └── purchase_flow.js   # 소수 트래픽: 로그인 → 장바구니 → 구매
├── smoke.js                 # 최소 검증 (VU 1, 5회 반복)
├── load.js                    # 목표 부하 (VU 100, 5분)
└── stress.js                    # 한계치 탐색 (VU 최대 750까지)
```

`browse`와 `purchase_flow`에 배분하는 VU 비율은, 이벤트 합성 시 정한
view:cart:purchase ≈ 10:3:1 비율을 참고해 대략 4:1로 잡았다 (조정 가능).

## 실행 순서 (반드시 이 순서로)

### 1. 스모크 테스트 — 스크립트 자체가 도는지 먼저 확인

```bash
k6 run -e PROJECT_ROOT=$(pwd) loadtest/k6/smoke.js
```

VU 1개로 5번만 돈다. 여기서 에러가 나면 API 자체에 문제가 있는 것이니,
load/stress 로 넘어가기 전에 먼저 고친다.

### 2. 목표 부하 테스트

```bash
k6 run -e PROJECT_ROOT=$(pwd) loadtest/k6/load.js
```

ADR 0002의 잠정 기준(VU 100, 5분, 에러율 1% 미만, p95 500ms 미만)을 확인한다.
`BASE_URL`을 바꾸고 싶으면:

```bash
k6 run -e PROJECT_ROOT=$(pwd) -e BASE_URL=http://localhost:8000 loadtest/k6/load.js
```

### 3. 스트레스 테스트 — 한계점 찾기

```bash
k6 run -e PROJECT_ROOT=$(pwd) loadtest/k6/stress.js
```

load.js를 통과했다면, 어디까지 버티는지 확인한다. 결과 리포트에서
`http_req_duration`이 급격히 늘어나거나 `http_req_failed`가 튀는 지점의
VU 수를 기록해두면, 그게 현재 시스템의 실질적 한계치다.

## 결과 기록

각 실행 결과(특히 병목을 발견했을 때)는 `docs/perf/`에 날짜순으로 남긴다.
형식은 `001-baseline.md`, `002-after-rate-limiting.md` 처럼 "무엇을 바꾸고
다시 쟀는지"가 파일명만 봐도 보이게 한다.

## 결과 해석 시 볼 것

k6가 끝나면 터미널에 요약이 출력된다. 주로 보는 지표:

| 지표 | 의미 |
|---|---|
| `http_req_duration` (p95, p99) | 응답 시간 분포. p95가 갑자기 튀는 구간이 병목 신호 |
| `http_req_failed` | 실패율. 스레숄드(1%) 넘으면 실패로 표시됨 |
| `iterations` | 총 몇 번의 시나리오가 완료됐는지 (처리량 추정용) |
| `vus_max` | 최대 동시 가상 사용자 수 |

터미널 출력만으로 "왜" 느려졌는지는 알기 어렵다. 이후 단계(Prometheus +
Grafana)에서 서버 쪽 지표(DB 커넥션, Kafka lag, CPU 등)를 같이 봐야 원인을
특정할 수 있다 — 이게 ADR 프로세스의 다음 단계다.

## 재고 동시성 검증 시나리오 (adrs/0004)

일반적인 트래픽 혼합(browse/load/stress)과 달리, 이 시나리오들은 "한정된
재고를 가진 상품 하나"에 트래픽을 몰아서 비관적 락의 정합성을 검증한다.

```
scenarios/inventory_race.js      — 공용 구매 시도 로직 (1/2/3번이 공유)
inventory_race_light.js          — 시나리오 1: 서버 정상, 순수 동시성 검증
inventory_race_crash.js          — 시나리오 2/3 공용 실행기: 장애 상황에서 실행
clear_all_carts.sql              — 테스트 전 모든 사용자 장바구니 정리
setup_inventory_test.sql         — 테스트 전 재고를 원하는 값으로 세팅
snapshot_inventory_state.sh      — 재고/이벤트 상태를 스냅샷으로 저장 (전후 비교용)
compare_snapshots.sh             — 두 스냅샷의 차이를 계산해 정합성 판정
reset_pipeline_for_test.sh       — (최초 1회 참고용) DB/Kafka/Spark 전체 초기화.
                                    스냅샷 비교 방식을 쓰면 반복 테스트에는
                                    필요 없다 - 과거 누적과 무관하게 증가분만
                                    보기 때문.
verify_inventory_consistency.sql — (참고용) 절대값 기준 쿼리 모음. 과거 누적이
                                    섞여 부정확할 수 있어, 반복 테스트에는
                                    snapshot/compare 스크립트를 쓴다.

장애 주입은 외부에서 컨테이너를 강제로 죽이는 방식(docker kill을 별도
스크립트로 타이밍 맞춰 실행) 대신, `checkout()` 코드 안(Kafka 전송 후,
commit 전)에 크래시 지점을 심어뒀다. 이 지점은 환경변수가 아니라
컨테이너 안의 파일(`/tmp/chaos_crash_before_commit`) 존재 여부로 켜진다.
처음에는 환경변수(`CHAOS_CRASH_BEFORE_COMMIT=1`) 방식으로 만들었는데,
"매번" 크래시가 나서 재시작된 워커가 다음 요청에서 또 죽어 서버가
계속 응답 불가 상태로 남는 문제를 실제로 겪었다. 파일은 크래시
"직전에 스스로 지워지므로" 정확히 한 번만 재현된다.
```

### 시나리오 1: 순수 동시성 검증 (서버 부하 없음)

"재고보다 더 많이 팔리지 않는가"를 가장 단순한 조건에서 확인한다.

```bash
# 모든 사용자 장바구니 정리 (이전 테스트 잔재 제거)
docker exec -i projecte-postgres psql -U postgres -d projecte \
  < loadtest/k6/clear_all_carts.sql

# 재고를 정확한 값으로 세팅 (예: 3개)
docker exec -i projecte-postgres psql -U postgres -d projecte \
  -v product_id="'85123A'" -v stock=3 < loadtest/k6/setup_inventory_test.sql

# VU 10개가 딱 1번씩만 동시에 구매 시도
k6 run -e PROJECT_ROOT=$(pwd) -e TARGET_PRODUCT_ID=85123A -e VU_COUNT=10 \
  loadtest/k6/inventory_race_light.js
```

통과 기준: `purchase_success`가 세팅한 재고 수량과 같거나 그 이하, `purchase_connection_dropped`/`purchase_server_error`가 정확히 0.

### 시나리오 2: 서버 장애 주입 — DB 정합성 검증

"처리 도중 backend가 죽어도 재고/주문 데이터가 안전한가"를 확인한다.

**주의: 반드시 `WORKERS=2` 이상으로 먼저 재시작해야 한다.** 개발
모드(`--reload`, WORKERS 미지정/1)는 uvicorn이 "리로더 프로세스(PID 1)
+ 그 자식(실제 서버)" 구조인데, 이 리로더는 파일 변경 시 재시작하는
용도라 `os._exit()`처럼 자식이 예기치 않게 뚝 끊기는 상황에 대한
복구가 안정적이지 않다 (실제로 이 상태에서 컨테이너는 `Up`인데 그 안의
서버 프로세스만 죽어 응답이 전혀 없는 상태를 겪었다). `--workers` 모드
(WORKERS>=2)는 마스터가 워커를 감독하는 진짜 멀티프로세스 구조라, 워커가
죽으면 마스터가 즉시 새 워커를 띄운다 — 이 복구 로직이 이번 시나리오가
검증하려는 것("장애 후에도 서비스가 살아난다")과 정확히 맞물린다.

```bash
# 0. WORKERS=2 이상으로 재시작 (개발 모드 --reload 로는 이 시나리오가
#    깨진다 - 위 설명 참고)
WORKERS=2 docker compose up -d --force-recreate backend

# 크래시 플래그 파일 생성 (재시작 직후, 다시 새로 뜬 컨테이너에)
docker exec projecte-backend touch /tmp/chaos_crash_before_commit

# 장바구니 정리 (이전 테스트 잔재 제거) + 재고 세팅
docker exec -i projecte-postgres psql -U postgres -d projecte \
  < loadtest/k6/clear_all_carts.sql
docker exec -i projecte-postgres psql -U postgres -d projecte \
  -v product_id="'85123A'" -v stock=5 < loadtest/k6/setup_inventory_test.sql

# 테스트 직전 스냅샷
bash loadtest/k6/snapshot_inventory_state.sh before 85123A

# k6 실행 (재고를 확보하는 첫 구매가 크래시 지점에서 정확히 한 번만 죽는다.
# 그 이후 요청들은 재시작된 프로세스가 정상 처리한다)
k6 run -e PROJECT_ROOT=$(pwd) -e TARGET_PRODUCT_ID=85123A \
  -e VU_COUNT=10 -e DURATION=30s loadtest/k6/inventory_race_crash.js

# 테스트 직후 스냅샷 + 비교
bash loadtest/k6/snapshot_inventory_state.sh after 85123A
bash loadtest/k6/compare_snapshots.sh before after

# (선택, 별도 터미널) backend가 그 순간 죽고 살아나는지 관찰
docker compose logs backend -f
```

`compare_snapshots.sh`의 "DB 기준 구매 수(재고 감소분)"이 음수가 아니고,
초과 판매(세팅한 재고보다 많이 팔림)가 없어야 통과다. 추가로:

```bash
docker exec -i projecte-postgres psql -U postgres -d projecte -c "
SELECT pid, state, query, now() - state_change AS idle_duration
FROM pg_stat_activity
WHERE datname = 'projecte' AND state = 'idle in transaction'
ORDER BY state_change;
"
```

이 결과가 비어있어야(`idle in transaction`으로 남은 세션 없음) 완전히 통과다.

### 시나리오 3: 서버 장애 주입 — DB-Kafka 정합성 검증 (이중 쓰기 문제)

실행 방법은 시나리오 2와 완전히 같다(같은 `inventory_race_crash.js`,
같은 파일 플래그 크래시 주입, 같은 스냅샷 전후 비교 방식). 다만 확인하는
대상이 다르다 — DB 자체가 아니라
**DB와 Kafka(→ Spark → `product_stats`/`raw_events`) 사이의 불일치**를 본다.

우리 `checkout()` 구현은 Kafka 전송을 `db.commit()` **이전에** 하기 때문에,
이론적으로 두 방향의 불일치가 모두 가능하다.

- Kafka 전송 성공 후 커밋 전에 서버가 죽음 → Kafka 쪽(product_stats)에는 구매가 잡혔는데 DB 재고는 안 줄어든 상태
- 반대로 커밋은 됐는데 Kafka 전송이 유실됨 → DB는 줄었는데 Kafka 쪽엔 안 잡힌 상태

`compare_snapshots.sh`의 두 mismatch 값(DB vs raw_events, DB vs
product_stats)이 모두 0이어야 정합성이 지켜진 것이다. 0이 아니면 이중
쓰기 불일치가 실제로 재현된 것이다. 이 경우 근본 해법은 Outbox
패턴(재고 차감과 "Kafka로 보낼 이벤트 기록"을 하나의 DB 트랜잭션으로
묶고, 별도 워커가 그 기록을 읽어 Kafka로 전송)이며, 이건 이번 시나리오
결과에 따라 별도 문서로 검토한다.

**스냅샷 방식을 쓰는 이유**: `raw_events`/`product_stats`는 과거
테스트/사용 이력이 계속 누적되는 테이블이라, 절대값을 그대로 보면
"이번 테스트로 발생한 변화"를 알 수 없다 (실제로 이걸 놓치고 절대값을
봤다가 `mismatch = -1142` 같은 비정상적으로 큰 값이 나온 적이 있다 —
진짜 이중 쓰기 문제가 아니라 과거 누적 1147건이 그대로 섞여서였다).
전체를 매번 초기화하는 방법(`reset_pipeline_for_test.sh`)도 있지만
Kafka 토픽 재생성 + Spark 재시작이 필요해 무겁다. 스냅샷 전후 비교는
과거 누적이 얼마나 있든 상관없이 "증가분만" 정확히 격리해서 보므로,
반복 테스트에는 이 방식을 표준으로 쓴다.

### 시나리오 2/3를 다시 실행하려면

크래시는 1회성이라, 플래그 파일이 사라진 뒤 다시 재현하려면 매번
플래그 파일 생성 단계부터 다시 한다 (WORKERS 재시작은 필요 없다 —
컨테이너가 이미 `--workers` 모드로 떠 있는 상태를 유지하고 있으므로).

```bash
docker exec projecte-backend touch /tmp/chaos_crash_before_commit
bash loadtest/k6/snapshot_inventory_state.sh before 85123A
# ... k6 실행 ...
bash loadtest/k6/snapshot_inventory_state.sh after 85123A
bash loadtest/k6/compare_snapshots.sh before after
```