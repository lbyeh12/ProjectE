# 001: 1차 부하 테스트 (baseline)

## 언제

- 날짜: 2026-08-05
- 관련 ADR: ADR 0001(모니터링 도구 선정), ADR 0002(부하 테스트 도구 선정)
- 이 측정 직전에 무엇을 바꿨나: 기준선(baseline). k6 + Prometheus/Grafana를
  갖춘 뒤 처음 실행하는 부하 테스트.

## 실행 조건

- 스크립트: load (VU 100, browse 80 + purchase 20, 4분)
- 목표 VU: 100
- 지속 시간: 4분
- 실행 환경: 로컬 Docker Compose. 총 3회 실행하며 조건을 바꿈 (아래 각 라운드 참고)

---

## 라운드 1: 최초 실행 (계정 20개, VU 고정 배정)

### 결과 요약

| 지표 | 값 |
|---|---|
| http_req_duration p95 | 241.35ms |
| http_req_failed (전체) | 1.12% (THRESHOLDS 실패: rate<0.01 기준 초과) |
| 구매(`/purchase`) 실패율 | 21% (242/1198) |
| vus_max | 100 |

### 관찰된 병목

전체 에러율이 목표(1%)를 살짝 넘겼는데, 원인을 좁혀보니 **`/purchase`
엔드포인트만** 유독 실패율이 높았다(다른 API는 전부 99~100% 성공).
백엔드 로그를 확인한 결과 응답 코드는 500이 아니라 **400**
("장바구니가 비어 있습니다") — 서버 장애가 아니라 애플리케이션 로직상
정상적으로 발생한 에러였다.

**원인**: `purchase_flow.js`가 계정을 `(__VU - 1) % users.length`로
VU 번호에 고정 배정했는데, k6의 `ramping-vus`는 한 VU의 이전
iteration이 끝나기 전에 다음 iteration이 겹쳐 시작될 수 있다. 같은
계정을 쓰는 두 iteration이 동시에 돌면, 하나가 먼저 구매해서 장바구니를
비우고 나면 나머지 하나는 빈 장바구니로 `/purchase`를 호출하게 된다.

→ **애플리케이션 병목이 아니라 부하 테스트 스크립트의 계정 배정 방식
문제**로 판단.

### 다음 액션

- `purchase_flow.js`: 계정을 VU 고정 배정 → 매 iteration 무작위 선택으로 변경
- `load.js`: 준비 계정 수 20 → 50 (VU 대비 여유를 둬서 동시 충돌 확률을 낮춤)

---

## 라운드 2: 계정 무작위 배정 + 50개로 확충 (Spark 미실행)

### 결과 요약

| 지표 | 값 |
|---|---|
| http_req_duration p95 | 246.76ms |
| http_req_failed (전체) | 0.69% (THRESHOLDS 통과) |
| 구매(`/purchase`) 실패율 | 13% (146/1161) — 개선됐으나 완전히 제거되진 않음 |
| PostgreSQL active connections (projecte, state=active) | 1~2 유지 |
| vus_max | 100 |

### 관찰된 병목

전체 THRESHOLDS는 통과했다. `/purchase` 개별 실패율은 21% → 13%로
줄었지만 완전히 사라지진 않았다 — 무작위 배정으로 확률을 낮췄을 뿐,
완전히 0으로 만들 수는 없는 구조적 특성이다. 다만 이건 실제 서비스에서도
"같은 사용자가 이미 처리된 주문을 다시 시도"하는 것과 유사한 상황이라,
테스트 스크립트의 한계로 보고 이번 라운드에서는 더 파고들지 않기로 함.

**PostgreSQL 커넥션은 1~2개로 낮게 유지** — 이번 부하 수준(VU 100)에서는
DB가 병목이 아니라는 게 명확히 확인됨.

### 다음 액션

- DB는 병목 후보에서 제외
- Kafka consumer lag을 보려면 Spark를 같이 띄워야 함 → 라운드 3

---

## 라운드 3: Spark 동시 실행 (전체 스택 동시 구동)

### 결과 요약

| 지표 | 값 |
|---|---|
| http_req_duration p95 | 605.51ms (THRESHOLDS 실패: p95<500 기준 초과) |
| http_req_failed (전체) | 0.66% (THRESHOLDS는 통과) |
| 로그인 실패 | `EOF` 에러 발생 (`Post "http://localhost:8000/auth/login": EOF`) |
| vus_max | 100 |

### 관찰된 병목

p95가 246ms → 605ms로 크게 악화됐고, 서버가 연결을 끊어버리는 `EOF`
에러까지 발생했다. 처음엔 "진짜 애플리케이션 병목을 찾았다"고 생각했으나,
`docker stats`로 확인한 결과 **backend 컨테이너만이 아니라
전체 컨테이너(14개)가 골고루 CPU를 많이 쓰고 있었다.**

**결론**: 이건 애플리케이션 병목이 아니라 **로컬 테스트 환경(Mac 한 대)의
물리적 리소스 한계**다. 지금 로컬에서 동시에 돌고 있던 것:
- Docker 컨테이너 14개 (postgres, kafka, kafka-ui, airflow 4개, backend,
  frontend, dashboard, prometheus, grafana, exporter 2개)
- Spark(JVM, 별도 프로세스)
- k6 (VU 100)

이 모든 걸 로컬 머신 한 대가 동시에 감당하려니 리소스 경쟁이 발생한
것으로, 실제 운영 환경(컴포넌트별로 별도 서버/컨테이너에 분산 배포)이라면
발생하지 않을 문제로 판단한다.

**부수 발견**: 이 라운드를 진행하며 별개로, Spark Structured Streaming이
전통적인 Kafka consumer group 커밋을 하지 않아 `kafka-exporter`가 lag을
전혀 못 읽는 문제를 발견함 


---

## 종합 결론

| 관찰 | 판정 |
|---|---|
| DB 커넥션 | 병목 아님 (VU 100 기준) |
| p95 응답시간 (Spark 미실행) | 여유 있음 (246ms, 목표 500ms) |
| 구매 API 동시성 에러 | 테스트 스크립트 특성, 애플리케이션 버그 아님 |
| Spark 동시 실행 시 지연 악화 | 애플리케이션 병목 아님, 로컬 환경 리소스 한계 |


## Related

- Related ADRs: ADR 0001 (모니터링 도구 선정), ADR 0002 (부하 테스트 도구 선정)
- 이전 기록: 없음 (최초 기록)
