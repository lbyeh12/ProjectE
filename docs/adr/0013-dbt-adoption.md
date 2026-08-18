# ADR 0013: 분석 스키마 변환 로직에 dbt 도입

## Status

Accepted

## Context

`dimensional_model_etl.py`가 SCD2 변경 감지, fact_events 적재 같은
변환 SQL을 Python 문자열 안에 직접 담고 있다. SQL만 따로 테스트하거나
버전 이력을 보기 어렵고, "어느 모델이 어느 모델에 의존하는지"가
코드에 암묵적으로만 존재한다(`t1 >> [t2, t3] >> t4`로 사람이 순서를
직접 관리).

## Decision Drivers

- SQL을 독립적으로 테스트/디버깅할 수 있어야 함.
- 모델 간 의존 관계를 도구가 자동으로 추론해야 함(사람이 순서를
  직접 관리하지 않도록).
- 데이터 품질 검증 규칙을 변환 로직과 같은 곳에서 선언적으로
  관리할 수 있어야 함.
- CI에서 변환 로직 자체를 검증할 수 있어야 함.

## Considered Options

1. **dbt** — SQL 파일 하나가 모델(테이블) 하나. `ref()`로 모델 간
   의존성을 선언하면 dbt가 실행 순서를 자동 추론. YAML로 테스트
   선언 가능(`unique`, `not_null`, `accepted_range` 등). 데이터
   엔지니어링 실무 표준 도구.
2. **현재 방식 유지(Airflow raw SQL)** — 추가 학습/마이그레이션
   비용이 없지만, 변환 로직이 SQL/Python 어디에도 없이 늘어나는
   문제를 그대로 안고 감.
3. **자체 SQL 파일 로더 구현** — dbt의 핵심 기능(ref 자동 추론,
   테스트)을 직접 구현하는 것은 dbt를 재발명하는 것이라 배제.

## Decision

**dbt를 도입한다.** `dimensional_model_etl.py`의 SCD2/fact 변환
로직을 dbt 모델로 옮기고, Airflow는 `dbt run`, `dbt test`를
실행만 시키는 얇은 오케스트레이터로 역할을 축소한다.

```
dbt/
├── models/
│   ├── staging/stg_raw_events.sql
│   └── marts/
│       ├── dim_date.sql
│       ├── dim_product.sql   (incremental, SCD2)
│       ├── dim_user.sql      (incremental, SCD2)
│       └── fact_events.sql   (incremental)
├── tests/schema.yml           (unique/not_null/accepted_range 등)
└── dbt_project.yml
```

- `models/marts/*.sql`은 `{{ ref(...) }}`, `{{ source(...) }}`로
  의존성을 선언, dbt가 실행 순서를 자동 추론.
- `dimensional_model_etl.py`는 `BashOperator`로 `dbt run`,
  `dbt test`만 호출.
- CI에 dbt 전용 워크플로우를 추가해서, PR마다 `dbt compile`(SQL
  문법/참조 오류 검증)과 `dbt test`(품질 규칙)를 자동 실행.

## Consequences

- **좋아지는 점**: 변환 로직이 독립적으로 테스트 가능해짐. 모델
  의존성을 dbt가 자동 관리해 Airflow 코드가 단순해짐. CI에서 SQL
  변경의 회귀를 자동 감지.
- **감수해야 하는 점**: dbt라는 새 도구/문법을 학습해야 함. Python
  으로 표현하기 쉬운 복잡한 조건부 로직은 dbt의 Jinja 템플릿으로
  옮기면 오히려 가독성이 떨어질 수 있어, 모든 변환을 dbt로 옮기지는
  않는다(예: quarantine 판정처럼 pandas가 더 적합한 로직은 유지).
- **후속 작업**: Great Expectations 검증 규칙 중 dbt test로 대체
  가능한 부분 정리. SCD2 동작(만료+신규 버전 생성)은 schema.yml의
  정적 테스트로 검증 안 되므로, CI(`dbt-ci.yml`)에 원본 변경 →
  재실행 → 결과 assertion 형태의 회귀 테스트를 추가해 매 PR마다
  자동 검증되도록 함.

## Related

- Related ADRs: ADR 0008 (차원 모델링), ADR 0009 (데이터 품질 검증)
- Related Perfs: 없음
