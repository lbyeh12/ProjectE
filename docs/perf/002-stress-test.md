# 002: 스트레스 테스트 (VU 750)

## 언제

- 날짜: 2026-08-07
- 이 측정 직전에 무엇을 바꿨나: 001-baseline 이후 변경 없음. Spark는 끈 상태
  (baseline 라운드 3에서, Spark 동시 실행이 로컬 리소스 경쟁을 유발한다는
  걸 확인했기 때문에 이번엔 애플리케이션 자체만 격리해서 봄).

## 실행 조건

- 스크립트: stress (browse 최대 600 VU, purchase 최대 150 VU, 총 750 VU, 6분)
- 목표 VU: 750
- 지속 시간: 6분 (실제로는 중간에 --interrupt 로 중단됨, 아래 라운드 2 참고)
- 실행 환경: 로컬 Docker Compose, Spark 미실행

---

## 라운드 1: Kafka 파티션 1개 상태에서 실행

### 결과 요약

| 지표 | 값 |
|---|---|
| http_req_duration (평균) | 16.19s |
| http_req_duration p90/p95 | 60s (k6 타임아웃 상한에 도달) |
| http_req_failed | 100% (setup 이후 본 시나리오 단계) |
| 상품 목록(`GET /products`) 성공률 | 45% |
| 로그인(`POST /auth/login`) 성공률 | 44% |

### 관찰된 사실

- 구매 API만이 아니라 **상품 목록, 로그인 등 다른 API도 함께 실패**했다.
  (001-baseline에서는 구매 API만 실패했던 것과 다른 양상)
- `WARN Request Failed error="... request timeout"` 로그가 다수 발생 —
  서버가 60초 동안 응답을 못 준 요청이 있었다.
- k6 스크립트 내부에서 `TypeError: Cannot read property 'length' of
  undefined` 에러 발생 (`browse.js:27`) — `http.get` 응답이 타임아웃되어
  `listRes.body`가 비어있는 상태에서 `JSON.parse`를 시도해 발생한 것으로
  보인다 (서버 응답 실패의 파생 증상).
- Grafana에서 PostgreSQL 커넥션 상태를 확인한 결과: `state=active`는 2,
  `state=idle in transaction`은 15까지 증가한 것을 확인함.
- `kafka-topics.sh --describe` 결과 `user-events` 토픽의
  `PartitionCount`가 1임을 확인함 (`kafka_setup.py`에서 3으로 설정하려
  했으나, `KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`로 인해 FastAPI의 최초
  이벤트 전송 시점에 기본값(1)으로 자동 생성된 것으로 추정).

## 라운드 2: Kafka 파티션을 3개로 늘린 후 재실행

### 조치

```
docker exec ... kafka-topics.sh --alter --topic user-events --partitions 3
```

### 결과 요약

| 지표 | 값 |
|---|---|
| http_req_failed | 45.19% |
| checks_succeeded | 48.61% |
| 상품 목록 성공률 | 27% (라운드 1의 45%보다 오히려 낮음) |
| 상품 상세 성공률 | 89% |
| 로그인 성공률 | 23% (라운드 1의 44%보다 오히려 낮음) |
| view 이벤트 성공률 | 85% |
| 검색 성공률 | 90% |
| 장바구니 담기 성공률 | 90% |
| 구매 성공률 | 89% |

### 관찰된 사실

- **증상 동일** 
  Kafka 토픽의 파티션 수를 1개에서 3개로 늘려봤으나 증상이 개선되지
  않았다.
  상품 목록/로그인 성공률은 라운드 1보다 낮게 측정됐다 (단, 두 라운드의
  실행 조건이 완전히 동일하지는 않음 — 테스트를 완주하지 않고 중간에
  중단한 점, 이전 라운드의 DB 상태가 완전히 초기화되지 않았을 가능성 등
  변수가 있어 이 수치 차이 자체를 "파티션 증가로 악화됐다"고 해석하지는
  않는다. "개선되지 않았다"는 것만 확인된 사실이다).
- 이번에도 실패율이 높은 엔드포인트(상품 목록, 로그인)와 상대적으로
  괜찮은 엔드포인트(상품 상세, view 이벤트, 검색, 장바구니, 구매) 사이에
  뚜렷한 차이가 있었다.

## 라운드 3: idle in transaction 원인 진단

### 조치 

부하 테스트가 진행되는 동안 아래 쿼리로 idle in transaction 세션을 직접 조회했다.

sql
SELECT pid, state, query, state_change, now() - state_change AS idle_duration
FROM pg_stat_activity
WHERE datname = 'projecte' AND state = 'idle in transaction'
ORDER BY state_change;

### 관찰된 사실

조회된 idle in transaction 세션들의 마지막 실행 쿼리 중 하나가 SELECT ... FROM users ... (로그인 시 사용자 조회 쿼리)였다.
idle_duration이 00:03:17(3분 17초)로 측정됐다. 

## Related

- Related ADRs: ADR 0002
- Related Perfs: 001-baseline.md 