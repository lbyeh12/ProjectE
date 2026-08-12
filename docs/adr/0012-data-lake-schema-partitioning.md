# ADR 0012: 데이터 레이크 스키마/파티션 설계 (Glue Crawler + Athena)

## Status

Accepted

## Context

ADR 0011로 raw_events/fact_events를 S3에 Parquet으로 올렸지만,
아직 "파일 더미"일 뿐 SQL로 조회할 수 없다. Athena 같은 쿼리
엔진이 조회하려면, S3의 파일 구조를 테이블 스키마와 파티션으로
인식시켜야 한다.

## Decision Drivers

- 스키마를 사람이 일일이 DDL로 작성하지 않고, 실제 파일에서 자동
  추론되게 하고 싶음(파이프라인이 커져도 유지보수 부담이 적어야 함).
- 자주 쓰는 조회 패턴(특정 날짜 범위 조회)의 성능/비용을 고려해
  파티션 키를 정해야 함.
- 이미 ADR 0011에서 정한 S3 경로 구조(`dt=YYYY-MM-DD`)를 그대로
  활용해야 함.

## Considered Options

### 스키마 정의 방식

1. **Glue Crawler(자동 추론)** — S3 경로를 스캔해서 컬럼/타입을
   자동으로 알아내고 Glue Data Catalog에 테이블로 등록. 스키마가
   바뀌어도(예: fact_events에 컬럼 추가) 재실행으로 갱신 가능.
2. **수동 DDL(`CREATE EXTERNAL TABLE`)** — 스키마를 정확히 통제할
   수 있지만, 컬럼이 바뀔 때마다 DDL을 직접 고쳐야 함.

### 파티션 키

1. **dt(날짜)** — "최근 N일 조회", "일별 집계" 같은 날짜 범위
   조회가 이 프로젝트의 가장 흔한 접근 패턴. ADR 0011에서 이미
   이 구조로 S3에 올려뒀음.
2. **product_id** — 상품별 조회가 흔하다면 유리하지만, 상품
   종류가 많아 파티션 수가 지나치게 늘어날 위험(파티션 폭발).
3. **파티션 없음** — 구현이 가장 단순하지만, 조회 시 항상 전체
   데이터를 스캔해 비용/속도가 나빠짐.

## Decision

**Glue Crawler + dt 파티션을 채택한다.** 자동 추론으로 스키마
관리 부담을 낮추고, 이미 구축된 날짜 기준 S3 경로 구조를 그대로
파티션으로 활용한다.

```
Glue Database: projecte_lake
Glue Crawler 대상:
  s3://projecte-data-lake/raw/raw_events/      -> 테이블 raw_events
  s3://projecte-data-lake/curated/fact_events/ -> 테이블 fact_events
파티션 키: dt (경로의 dt=YYYY-MM-DD 에서 자동 인식)
```

검증 방법: Athena에서 `WHERE dt = '...'` 조건이 있는 쿼리와 없는
쿼리의 스캔 데이터량을 비교해, 파티션이 실제로 스캔 범위를 줄이는지
실측으로 확인한다.

## Consequences

- **좋아지는 점**: 스키마 변경에 유연하게 대응 가능. 날짜 범위
  조회 시 스캔 비용/속도가 크게 개선됨(Athena는 스캔한 데이터량
  기준으로 과금되므로 비용에도 직결).
- **감수해야 하는 점**: Crawler를 새 데이터가 쌓일 때마다(또는
  주기적으로) 재실행해야 카탈로그가 최신 상태를 유지한다. 상품
  단위 조회가 잦아지면 이 파티션 전략이 오히려 비효율적일 수 있어,
  접근 패턴이 바뀌면 재검토 필요.
- **후속 작업**: 파티션 유무에 따른 스캔량 비교를 perf 문서로 기록.

## Related

- Related ADRs: ADR 0011 (AWS 클라우드 데이터 레이크 연동)
- Related Perfs: 없음
