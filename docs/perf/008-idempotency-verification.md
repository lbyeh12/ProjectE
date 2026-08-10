# 008: 멱등성 키 검증

## 언제

- 날짜: 2026-08-10
- 관련 ADR: ADR 0006 (멱등성 키 저장소로 Redis 선택)
- 이 측정 직전에 무엇을 바꿨나: checkout()에 Idempotency-Key 헤더
  지원 추가, Redis SET NX 기반 중복 검사 구현.

## 실행 조건

- 스크립트: 없음 (curl로 수동 검증)
- 목표 VU: 해당 없음
- 지속 시간: 해당 없음
- 실행 환경: 로컬 Docker Compose

## 결과 요약

같은 Idempotency-Key로 `/purchase`를 7회 연속 호출.

| 지표 | 값 |
|---|---|
| API 응답 | 7회 모두 동일 (purchased_items=1, total_price=6000.0) |
| 재고 감소분 | 1 (5 → 4) |
| raw_events(Kafka 경로) 반영 건수 | 1 |

## 관찰된 병목

없음. 7번의 중복 요청 중 1번만 실제로 처리되고 나머지는 캐싱된
결과를 그대로 반환했다. DB, Kafka/Spark, 클라이언트 응답 세 층위
모두에서 정합성이 확인됐다.

## Related

- Related ADRs: ADR 0006 (멱등성 키 저장소로 Redis 선택), ADR 0005 (Outbox 패턴 도입)
- Related Perfs: 007-outbox-verification.md
