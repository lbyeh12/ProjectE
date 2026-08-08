# ADR 0003: 로그 수집 도구 선택

## Status

Accepted

## Context

ADR 0001에서 Prometheus + Grafana를 도입하면서, 로그 수집(Loki)은 그 범위 밖에 두었다. `docs/perf/002-stress-test.md`, `003-worker-scaling.md`에서
실제로 그 필요성이 확인됐다: VU가 최대치 근처에 도달하는 시점에
`POST /auth/login`, `POST /events` 등에서 EOF(연결 끊김)와 timeout이
발생했는데, Prometheus 메트릭만으로는 "무엇이 실패했는가(집계된 숫자)"는
보여도 "왜 그 순간 연결이 끊겼는지(원인)"는 알 수 없었다. 

## Decision Drivers

- Grafana를 "단일 관측 화면"으로 기능하게 할 것
- 무료로 사용 가능해야 함.
- 가벼운 도구일 것. (로컬 환경 고려)

## Considered Options

1. **Grafana Loki** 
   - 로그 내용 전체가 아니라 라벨(메타데이터)만 인덱싱하고, 실제 로그 본문은 압축해서 저장. 
   - Prometheus+Grafana와 호환 우수
   - 로그 내용 자체에 대한 전문 검색(ad-hoc full-text search)은 느리다.

2. **ELK(Elasticsearch+Logstash+Kibana)** 
   - 로그 내용 전체를 인덱싱해 검색 능력이 가장 강력하다. 
   - 최신 버전은 라이선스가 SSPL로 바뀌어 완전한 오픈소스가 아님
   - JVM 기반 클러스터라 리소스 사용량이 크다.

3. **OpenSearch** 
   - ELK의 라이선스 문제 때문에 AWS가 포크한 완전 오픈소스(Apache 2.0) 버전. 
   - 클러스터 운영 부담은 ELK와 비슷하게 크다.

4. **OpenObserve** 
   - 메트릭/로그/트레이스를 한 바이너리로 통합, 객체 스토리지 기반 컬럼 압축으로 저장 비용이 매우 낮다.
   - SQL 기반 쿼리로 진입장벽이 낮다.
   - 관측 화면 제공


## Decision

**Loki를 채택** 

1. ADR 0001에서 세운 "Grafana 단일 화면" 원칙을 그대로 유지할 수 있다

2. Prometheus와 동일한 라벨 기반 모델이라, 이미 우리가 짠 PromQL
   쿼리(예: `{name=~"projecte-.*"}` 식의 라벨 필터링)와 사고방식 유지

3. 로그 내용 전체를 인덱싱하지 않아 리소스 사용량이 낮다.

로그 수집기(shipper)는 Promtail을 쓴다. 

## Consequences

- **좋아지는 점**: Grafana에서 메트릭 그래프(예: 에러율 급증 구간)를
  본 뒤, 같은 화면에서 그 시간대의 실제 로그로 바로 넘어가 원인을
  확인할 수 있게 된다.

- **감수해야 하는 점**: 로그 "내용"에 대한 자유로운 전문 검색은
  느리다. 나중에 복잡한 로그 분석(예: 특정 문자열이 로그 전체에서
  몇 번 나왔는지 집계)이 필요해지면, 이 결정을 재검토해야 할 수
  있다.


## Related

- Related Perfs: docs/perf/002-stress-test.md, docs/perf/003-worker-scaling.md
