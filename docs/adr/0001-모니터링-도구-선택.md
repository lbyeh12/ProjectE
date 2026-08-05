# ADR 0001: 모니터링 도구 선택

## Status

Accepted

## Context

지금까지 만든 파이프라인(React → FastAPI → Kafka → Spark → PostgreSQL,
그리고 Airflow 배치)은 "정상적으로 동작하는가"는 pytest/CI로 검증했지만,
"트래픽이 몰렸을 때 시스템 내부에서 무슨 일이 일어나는가"는 전혀 볼 수
없는 상태다.

## Decision Drivers

- 무료로 사용 가능해야 한다. (프로젝트용)
- PostgreSQL/Kafka와 쉬운 연동이 가능해야한다.
- 인지도 높은 도구일 것.

## Considered Options

### 오픈소스

**Prometheus + Grafana, Zabbix, Nagios**
- 직접 설치·운영이 가능하다.
- 라이선스 비용 없음, 높은 커스터마이징 자유도
- 구축·유지 인력 필요, 초기 설정 복잡

### 클라우드

**AWS CloudWatch, Azure Monitor, GCP Cloud Monitoring**
- 클라우드 플랫폼 네이티브 연동
- 플랫폼 리소스 수집 용이, 별도 에이전트 부담 적음
- 멀티·하이브리드 환경 통합 어려움

### SaaS
**WhaTap, Datadog, New Relic**
- 클라우드 기반 완전 관리형
- 빠른 도입, 전문 인력 부담 완화, 통합 뷰 제공
- 월정 비용 발생, 외부 데이터 전송 시 보안 검토 필요

## Decision

**Prometheus + Grafana를 채택** 

1. 무료로 사용 가능 (지금 docker-compose에 그대로 추가 가능)
2. PostgreSQL/Kafka 전용 exporter가 성숙해서 우리 스택에 바로 적용 가능
3. 초기 설정이 비교적 복잡하지만 학습 목적으로는 적합

## Consequences

- **좋아지는 점**: FastAPI 요청 지표(`/metrics`), PostgreSQL 커넥션 수,
  Kafka consumer lag을 Grafana 대시보드 하나에서 실시간으로 볼 수
  있게 됨.
- **감수해야 하는 점**: Loki, Tempo를 도입하지 않으므로 로그/트레이싱은 범위 밖임. "이 요청이 정확히
  어디서 얼마나 걸렸는지" 같은 세밀한 추적은 불가능


## Related
- Supersedes: 없음
- Related ADRs: ADR-0002

