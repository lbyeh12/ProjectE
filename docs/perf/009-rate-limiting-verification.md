# 009: Rate Limiting 검증

## 언제

- 날짜: 2026-08-10
- 관련 ADR: ADR 0007 (Rate Limiting 도입)
- 이 측정 직전에 무엇을 바꿨나: /auth/login, /purchase에 Redis 기반
  Rate Limiting 적용 (고정 윈도우, INCR+EXPIRE).

## 실행 조건

- 스크립트: 없음 (curl로 수동 검증)
- 목표 VU: 해당 없음
- 지속 시간: 해당 없음
- 실행 환경: 로컬 Docker Compose

## 결과 요약

같은 계정으로 `/auth/login`을 6회 연속 호출 (제한: 1분 5회).

| 시도 | 응답 |
|---|---|
| 1~5번째 | 401 (비밀번호 불일치, 정상 처리됨 - bcrypt까지 도달) |
| 6번째 | 429 (Rate Limit 초과, bcrypt 도달 전 차단) |

## 관찰된 병목

없음. 의도한 대로 정확히 5회까지 bcrypt 검증까지 도달했고, 6번째는
Redis 카운터 확인만으로 즉시 거절됐다.

## 다음 액션

- Outbox Relay의 at-least-once 특성 보완(Consumer 측 멱등성)으로 이동,
  또는 데이터 엔지니어링 쪽 보강(Airflow 재시도 등)으로 이동

## Related

- Related ADRs: ADR 0007 (Rate Limiting 도입), ADR 0006 (멱등성 키 저장소로 Redis 선택)
- Related Perfs: 008-idempotency-verification.md
