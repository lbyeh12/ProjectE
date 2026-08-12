# ADR 0010: Airflow 파이프라인 안정성 (재시도/알림/백필)

## Status

Accepted

## Context

지금 `daily_etl` DAG은 실패해도 재시도하지 않고, 아무에게도
알리지 않는다. 오늘 날짜만 계산하도록 하드코딩되어 있어, 특정
과거 날짜의 로직이 잘못됐다는 걸 나중에 알아도 그 날짜만 다시
계산할 방법이 없다. 실무에서는 "새벽에 배치가 죽으면 사람이 알아야
한다"와 "지난주 로직이 잘못됐으면 다시 돌릴 수 있어야 한다"가
기본 요구사항이다.

## Decision Drivers

- 배치 실패 시 자동으로 재시도해야 함.
- 재시도로도 안 되면 담당자에게 알려야 함.
- 특정 과거 날짜만 골라서 재실행(backfill) 가능해야 함.
- 기존 Airflow 인프라 안에서 해결해야 함(새 컴포넌트 최소화).

## Considered Options

1. **Airflow 내장 기능(retries, execution_date, Slack Webhook
   Operator)으로 해결** — 별도 도구 없이 Airflow 표준 기능만으로
   구성. 학습 비용이 낮고 실무에서도 이 조합이 흔함.
2. **외부 모니터링 도구(Datadog, PagerDuty 등) 연동** — 알림
   기능은 더 강력하지만, 개인 프로젝트 규모에 비해 과함 이미
   Prometheus+Grafana를 갖추고 있어 중복 투자.
3. **재시도/알림 없이 수동 대응** — 지금 상태 유지. 실무 요구사항에
   대응하지 못함.

## Decision

**Airflow 내장 기능으로 해결한다.**

- DAG 기본 설정에 `retries=3`, `retry_delay=5분` 추가.
- 최종 실패 시 Slack Webhook으로 알림(`on_failure_callback`).
- DAG을 "오늘 날짜 하드코딩"에서 `execution_date` 기반으로
  바꿔서, Airflow UI에서 특정 과거 날짜를 선택해 재실행(backfill)
  가능하게 한다.

## Consequences

- **좋아지는 점**: 일시적 장애(DB 커넥션 순간 끊김 등)는 재시도로
  자동 복구된다. 완전히 실패하면 알림이 오므로 방치되지 않는다.
  과거 특정 날짜의 로직 오류를 그 날짜만 다시 계산해 수정할 수
  있다.
- **감수해야 하는 점**: 재시도가 오히려 멱등성이 없는 태스크에서는
  중복 실행 위험을 만들 수 있다 — 각 태스크가 재실행되어도 안전한지
  (예: INSERT 대신 UPSERT) 함께 점검해야 한다.
- **후속 작업**: daily_etl 내 각 태스크의 멱등성 재점검.

## Related

- Related ADRs: ADR 0006 (멱등성 키 저장소로 Redis 선택, 개념적으로 연결)
- Related Perfs: 없음
