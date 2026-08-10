# 007: Outbox 패턴 적용 후 재검증

## 언제

- 날짜: 2026-08-09
- 관련 ADR: ADR 0005 (Outbox 패턴 도입)
- 이 측정 직전에 무엇을 바꿨나: checkout()/log_event()가 Kafka로
  직접 전송하는 대신 outbox_events에 기록하도록 변경, 별도
  Relay(scripts/outbox_relay.py)가 폴링해 전송하도록 구현.

## 실행 조건

- 스크립트: inventory_race_crash.js (시나리오 3과 동일 조건)
- 목표 VU: 50
- 지속 시간: 30초
- 실행 환경: 로컬 Docker Compose, WORKERS=2, Spark Streaming 실행 중,
  outbox-relay 실행 중 (POLL_INTERVAL_SECONDS=2)

## 결과 요약

| 지표 | 006 (Outbox 적용 전) | 007 (Outbox 적용 후) |
|---|---|---|
| DB 기준 구매 수 (재고 감소분) | 5 | 5 |
| raw_events 증가분 | 6 | 5 |
| product_stats 증가분 | 6 | 5 |
| mismatch (DB vs raw_events) | -1 | 0 |
| mismatch (DB vs product_stats) | -1 | 0 |

## 관찰된 병목

**이중 쓰기 불일치가 완전히 해소됨.** 재고 차감과 outbox_events 기록이
같은 트랜잭션에 묶이면서, 커밋 직전 크래시가 나도 둘 다 함께
롤백되어 DB와 Kafka(→ Spark) 양쪽이 항상 일치하게 됐다.

재검증 과정에서 두 가지 잡음을 확인하고 배제했다.

1. **outbox-relay의 PYTHONPATH 문제**: `python scripts/outbox_relay.py`
   실행 시 `app` 패키지를 못 찾는 ModuleNotFoundError 발생.
   PYTHONPATH=/app 환경변수 추가로 해결.
2. **product_stats의 일시적 오차(42로 튐)**: outputMode("complete")로
   전체 재계산하는 특성상, Spark가 그 사이 밀려있던 이전 테스트의
   이벤트를 한꺼번에 반영하는 시점과 스냅샷 타이밍이 겹쳐 발생.
   Spark를 재시작한 뒤 재측정하니 정상치로 돌아옴 — 이중 쓰기와
   무관한 별개의 타이밍 이슈였음.

## 다음 액션

- 백엔드 이슈 마무리 단계로 이동 (멱등성 키, Rate Limiting)
- Outbox Relay의 at-least-once 특성(중복 전송 가능성)에 대한
  Consumer 측 멱등성 처리는 별도 과제로 유지

## Related

- Related ADRs: ADR 0005 (Outbox 패턴 도입), ADR 0004 (재고 동시성 제어 방식 선택)
- 이전 기록: 006-inventory-race.md
