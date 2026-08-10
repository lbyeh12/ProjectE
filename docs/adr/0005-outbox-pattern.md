# ADR 0005: 이중 쓰기 문제 해결을 위한 Outbox 패턴 도입

## Status

Accepted

## Context

`docs/perf/006-inventory-race.md`에서 checkout()의 이중 쓰기 문제가
실제로 재현됐다. Kafka 전송을 db.commit() 이전에 하는 구조라, 재고
차감 후 커밋 전에 서버가 죽으면 DB 트랜잭션은 롤백되지만 Kafka
메시지는 이미 나가 있어 되돌릴 수 없다. 실측에서 DB 기준 구매 5건에
Kafka 기준 6건으로 mismatch가 확인됐다.

## Decision Drivers

- 재고 차감과 이벤트 발행이 "둘 다 성공하거나 둘 다 실패"해야 한다.
- 우리 규모(로컬 개발, 컴포넌트 적음)에 맞는 복잡도여야 한다.
- 실시간성은 일부 희생 가능 (프로젝트의 "실시간 집계"는 재고
  자체가 아니라 통계 성격이라, 몇 초 지연은 감수 가능하다고 판단).

## Considered Options

1. **Transactional Outbox 패턴**
   - Kafka로 직접 안 보내고, 같은 DB 트랜잭션에 "보낼 이벤트"를
     outbox 테이블로 같이 기록. 별도 Relay가 폴링해서 Kafka로 전송.
   - 원자성이 DB 트랜잭션만으로 보장됨. 업계 표준.
   - Relay 프로세스가 추가로 필요하고, 폴링 주기만큼 지연 생김.
2. **CDC (Debezium)**
   - DB의 WAL을 직접 읽어 변경을 Kafka로 스트리밍.
   - 실시간성이 더 좋지만, 별도 인프라(Debezium)가 필요해 우리
     로컬 환경(이미 컴포넌트 많음)에 부담이 큼.
3. **Saga 패턴**
   - 여러 서비스에 걸친 워크플로우를 보상 트랜잭션으로 조율.
   - 우리는 서비스가 backend 하나뿐이라 조율할 대상 자체가 없음.
     대상 문제와 층위가 다름.
4. **멱등성만으로 대응 (완벽한 원자성 포기)**
   - 중복 발행을 인정하고 Consumer 쪽에서 걸러냄.
   - 구조는 단순하지만 "결과적 정합성"만 보장, 이번엔 원인 자체를
     막는 방향을 우선하기로 함.

## Decision

**Transactional Outbox 패턴을 채택한다.** 우리 상황(단일 서비스,
DB+메시지큐 이중 쓰기)에 가장 직접적으로 맞고, CDC/Saga 대비 복잡도가
낮다.

구현 방향:
- `outbox_events` 테이블 신설 (기존 `raw_events`는 use_kafka=false
  폴백 저장소로 목적이 달라 겸용하지 않음)
- checkout()은 Kafka로 직접 안 보내고 outbox_events에 기록, 재고
  차감과 같은 트랜잭션으로 묶음
- 별도 Python 스크립트(Relay)가 주기적으로 폴링해 Kafka로 전송,
  성공 시 sent_at 기록 (FastAPI 백그라운드 태스크는 요청 생명주기에
  묶여 재시도 주체가 없어 제외)
- Relay는 docker-compose에 별도 서비스로 추가

## Consequences

- **좋아지는 점**: 재고 차감과 이벤트 발행이 원자적으로 묶여, 커밋
  전 크래시가 나도 이중 쓰기가 발생하지 않는다.
- **감수해야 하는 점**: Relay 폴링 주기만큼 이벤트 반영 지연이
  생긴다. Relay가 Kafka 전송 성공 후 sent_at 기록 전에 죽으면
  중복 전송 가능성은 남는다 (at-least-once) — Consumer(Spark) 측
  멱등성 처리는 별도 과제로 남긴다.
- **후속 작업**: 구현 후 시나리오 3(inventory_race_crash.js)로
  재검증, mismatch가 0이 되는지 확인.

## Related

- Related ADRs: ADR 0004 (재고 동시성 제어 방식 선택)
- Related Perfs: docs/perf/006-inventory-race.md
