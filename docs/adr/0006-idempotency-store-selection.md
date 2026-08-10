# ADR 0006: 멱등성 키 저장소로 Redis 선택

## Status

Accepted

## Context

`docs/perf/006-inventory-race.md`에서 커밋은 성공했으나 응답이
클라이언트에 전달되지 못한 케이스가 발견됐다. 재시도 시 중복 처리를
막을 멱등성 키가 필요하다. 검사 저장소는 매 요청마다 조회되므로
DB(PostgreSQL)에 부하를 더하지 않는 별도 저장소가 필요하다. 이후
Rate Limiting에도 같은 저장소를 재사용할 계획이다.

## Decision Drivers

- 매 요청마다 빠르게 조회/기록해야 함.
- 여러 워커가 동시에 같은 키를 두고 경쟁해도 원자적 연산(SET NX 등)
  으로 정확히 한 번만 처리되어야 함.
- TTL(자동 만료)을 지원해야 함.
- 이후 Rate Limiting의 카운터 연산에도 재사용.

## Considered Options

1. **Redis** — 시장 점유율 82%로 압도적. 2025년 5월부터 AGPLv3가
   추가되었다.
2. **Valkey** — Redis 7.2.4를 BSD-3로 포크한 API 호환 버전. 기술적
   차이는 없음.
3. **Memcached** — 원자적 연산(NX)과 자료구조가 제한적이라 Rate
   Limiting의 카운터 연산까지 고려하면 기능 부족.

## Decision

**Redis를 채택한다.** 시장 점유율이 압도적이고, 이미 이 프로젝트에
같은 라이선스(AGPLv3)의 Grafana, k6, Loki를 쓰고 있어 Redis를 사용한다.
## Consequences

- **좋아지는 점**: 멱등성 검사가 DB와 분리되어 DB 병목(docs/perf/002,
  003)에 영향을 안 준다. SET NX + TTL로 멱등성 로직 구현 가능. Rate
  Limiting도 같은 인스턴스 재사용 가능.
- **감수해야 하는 점**: 관리해야할 컨테이너가 하나 더 늘어난다(이미 17개). 


## Related

- Related ADRs: ADR 0005 (Outbox 패턴 도입)
- Related Perfs: docs/perf/006-inventory-race.md
