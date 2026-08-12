# 010: CI 통합 테스트 보강

## 언제

- 날짜: 2026-08-10
- 관련 ADR: ADR 0004, 0005, 0006, 0007
- 이 측정 직전에 무엇을 바꿨나: 재고 동시성/Outbox/멱등성 키/Rate
  Limiting을 검증하는 pytest 테스트 추가, CI에 Redis 서비스 추가.

## 실행 조건

- 스크립트: pytest (backend/tests/)
- 목표 VU: 해당 없음
- 지속 시간: 해당 없음
- 실행 환경: 로컬 (postgres/redis 별도 컨테이너), GitHub Actions

## 결과 요약

| 항목 | 값 |
|---|---|
| 전체 테스트 수 | 35 |
| 통과 | 35 |

## 관찰된 병목

기존 테스트가 재고 컬럼 도입 이후 깨져 있었다: `sample_product`
fixture에 재고가 없어 구매 성공 테스트가 409로 실패할 상황이었다.
`stock=100`을 추가해 해결.

Redis를 매 테스트 전후로 비우려던 `_isolate_redis` fixture가 `client` fixture와의 의존
관계가 없어, pytest의 teardown 순서(설정의 역순)상 `client`의
lifespan shutdown(Redis 연결 종료, `_client=None`)이 먼저 실행된
뒤 flush를 시도해 조용히 무시됐다. 그 결과 고정된 테스트 계정의
로그인 Rate Limit 카운터가 테스트 전체에 걸쳐 누적되어, 무관한
다른 테스트들이 429를 받고 `access_token` 없음으로 KeyError가
나는 현상으로 나타났다. `_isolate_redis(client)`로 의존성을
명시해 teardown 순서를 강제하여 해결.

이건 애플리케이션 로직의 문제가 아니라 테스트 인프라 설계의 문제였다.

## Related

- Related ADRs: ADR 0004, 0005, 0006, 0007
\
