# ADR 0007: Rate Limiting 도입

## Status

Accepted

## Context

로그인(`/auth/login`)은 bcrypt 검증 때문에 CPU 비용이 크다
(docs/perf/002-stress-test.md, 003-worker-scaling.md). 같은 계정에
비밀번호를 반복 시도하는 브루트포스 공격은 이 bcrypt 연산을 그대로
반복시켜 서버 자원을 소모시킨다. `/purchase`도 한정 재고에 봇이
반복적으로 요청을 보내는 경우 동일한 문제가 생긴다. 현재 시스템은
데이터 정합성(비관적 락, Outbox, 멱등성 키)은 갖췄지만, 과도한
반복 요청 자체를 막는 장치가 없다.

## Decision Drivers

- 짧은 시간에 반복되는 요청(브루트포스, 봇)을 차단해야 함.
- 워커가 여러 개(WORKERS=4)이므로 카운터를 워커 간에 공유해야 정확한
  제한이 됨.
- 거절된 요청은 bcrypt 등 무거운 연산 이전에 막아야 자원 절감 효과가
  있음.

## Considered Options

1. **애플리케이션 코드에서 Redis 카운터로 직접 구현** — ADR 0006에서
   이미 도입한 Redis를 재사용. 별도 인프라 추가 없음.
2. **API Gateway/리버스 프록시에서 처리 (Nginx rate limiting 등)** —
   애플리케이션 코드를 안 건드리지만, 지금 구조에 리버스 프록시가
   없어 새 컴포넌트 도입이 필요함.
3. **slowapi 등 기존 라이브러리 사용** — Flask-Limiter를 본뜬 FastAPI
   전용 라이브러리, Redis 백엔드 지원.

## Decision

**Redis 기반으로, 애플리케이션 코드에서 직접 구현한다.** 이미 ADR
0006으로 Redis가 있어 인프라 추가가 없고, 우리 요청 흐름(로그인,
구매)에 맞춰 세밀하게 제한을 걸 수 있다. 리버스 프록시 도입은 지금
규모에 비해 과하다고 판단해 제외한다.

- `/auth/login`: 계정 기준으로 짧은 시간 내 반복 시도 제한
- `/purchase`: 동일 사용자의 과도한 반복 요청 제한
- 제한 초과 시 429 Too Many Requests로 응답, bcrypt 등 무거운 연산
  이전에 거절

## Consequences

- **좋아지는 점**: 브루트포스/봇성 반복 요청이 bcrypt 등 무거운 연산에
  도달하기 전에 차단되어 서버 자원을 아낀다.
- **감수해야 하는 점**: Redis 장애 시 Rate Limiting 자체가 동작하지
  않을 수 있음 — 이 경우 요청을 차단할지 통과시킬지 정책 결정 필요.
- **후속 작업**: `/auth/login`, `/purchase`에 우선 적용 후 검증.

## Related

- Related ADRs: ADR 0006 (멱등성 키 저장소로 Redis 선택)
- Related Perfs: docs/perf/002-stress-test.md, docs/perf/003-worker-scaling.md
