# ADR 0002: 부하 테스트 도구 선정

## Status

Accepted

## Context

만든 파이프라인(React → FastAPI → Kafka → Spark → PostgreSQL, 그리고
Airflow 배치)은 "정상적으로 동작하는가"는 pytest/CI로 검증했지만,
"트래픽이 몰렸을 때도 버티는가"는 검증한 적이 없다.

실제로 부하를 걸어서 어디가 먼저 무너지는지 확인하고, 그 병목에 맞는 항목을 수정하는 방식으로 진행한다.
이를 위해 실제로 부하를 줄 수 있는 테스트를 설계할 수 있는 도구를 선정한다.

## Decision Drivers

- 실제 사용자 행동과 유사한 트래픽 패턴을 설계 가능해야한다. 
- 순수 파이썬 스크립트로 설계하는 결과보다 더 쉽고 직관적으로 사용가능해야 한다.


## Considered Options

**k6** — Go 기반 단일 바이너리, JS/TS로 스크립트 작성. Grafana
   생태계와 통합이 좋다는 평가가 많았고, 2026년 기준 신규 프로젝트의
   사실상 표준으로 언급됨.
**Locust** — 순수 Python으로 스크립트 작성 가능해 우리 스택(Python
   백엔드)과 잘 맞음. 다만 단일 노드 처리량이 k6보다 낮고, Grafana
   연동이 비교적 어려움.
**JMeter** — 오래되고 검증된 도구, 프로토콜 지원이 넓음. 하지만
   GUI 기반 `.jmx`(XML) 파일이라 버전 관리와 코드 리뷰가 어려움.

## Decision

**k6를 채택**

1. 코드(JS)로 버전 관리되어 우리 저장소 구조와 일관됨
2. Prometheus/Grafana와 자연스럽게 연동됨 (k6는 Prometheus remote-write, Grafana Cloud 연동을 공식 지원 — 부하 테스트 결과와 서버 메트릭을 같은 화면에서 겹쳐 볼 수 있음)


## Consequences

- **좋아지는 점**: 부하를 스크립트로 재현 가능해졌고, 저장소에 코드로
  남아 누구나 같은 방식으로 재실행가능. 
  Grafana 대시보드로 부하 테스트 중 서버 상태를 실시간으로 볼 수 있다.
- **감수해야 하는 점**: k6는 JS 런타임이 Node.js가 아니라 자체 구현
  (goja)이라, npm 패키지 생태계를 그대로 못 씀. 스크립트 재사용에
  제약이 있음.


## Related

- Superseded by: 없음 (진행 중)
- Related ADRs: ADR 0001