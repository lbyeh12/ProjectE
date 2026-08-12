# ADR 0008: 차원 모델링(Star Schema) 도입

## Status

Accepted

## Context

지금 저장 구조는 `raw_events`(원본 이벤트)와 `product_stats`,
`traffic_stats`(단순 집계 테이블)뿐이라 분석가/BI 도구가 붙기
어렵다. "날짜별×상품별×사용자별로 매출/퍼널을 자유롭게 잘라볼 수
있는가" 같은 다차원 분석에 대응하지 못한다. 데이터 엔지니어 직무는
보통 이런 분석 친화적 모델링 역량을 요구한다.

## Decision Drivers

- 날짜/상품/사용자 축으로 매출뿐 아니라 view/search/cart 등 퍼널
  전체를 집계할 수 있어야 함.
- 상품 가격이나 사용자 속성이 바뀌어도, 과거 거래를 "그 시점 기준"
  값으로 정확히 재구성할 수 있어야 함(이력 추적).
- 기존 배치 인프라(Airflow `daily_etl`)를 재사용해 새 컴포넌트를
  추가하지 않아야 함.
- 프로젝트 규모상 과도하게 정규화하지 않아야 함.

## Considered Options

### 사실 테이블 범위

1. **fact_events (전체 이벤트 단일 사실 테이블)** — view/search/
   add_to_cart/purchase/refund/signup/login 전부를 한 테이블에,
   원본 이벤트 1건당 1행으로 담는다. `event_type`을 degenerate
   dimension으로 두고, `revenue`는 purchase일 때만 값을 가진다.
   퍼널 분석과 매출 분석을 하나의 테이블로 처리 가능.
2. **fact_purchases (구매만)** — 구매 이벤트만 다룸. 매출 분석은
   되지만 "조회 대비 구매 전환율" 같은 퍼널 분석이 안 됨.

### 차원 이력 관리

1. **Type 2 SCD (이력 보존)** — 차원 속성(상품 가격, 사용자 국가 등)이
   바뀌면 기존 행은 만료 처리하고 새 surrogate key로 새 행을 추가.
   과거 사실 테이블의 키는 "그 시점의" 차원 값을 그대로 가리켜,
   나중에 속성이 바뀌어도 과거 거래를 왜곡 없이 재구성 가능.
   변경 감지/만료 처리 로직이 추가로 필요함.
2. **Type 1 SCD (덮어쓰기)** — 구현이 단순하지만 이력이 사라져서,
   "그때 그 가격"을 나중에 못 복원함.

## Decision

**fact_events(전체 이벤트) + Type 2 SCD(이력 보존)를 채택한다.**

```
dim_date(date_key, full_date, year, month, day, day_of_week, is_weekend)

dim_product(product_key, product_id, description, price,
            effective_date, expiration_date, is_current)

dim_user(user_key, user_id, country,
         effective_date, expiration_date, is_current)

fact_events(event_key, date_key, product_key, user_key,
            event_type, price, revenue, source_event_id)
```

- `fact_events`는 원본 이벤트(`raw_events`) 1건당 1행. `revenue`는
  `event_type='purchase'`일 때만 `price`, 그 외에는 0으로 둔다.
  `product_key`/`user_key`는 상품/사용자 정보가 없는 이벤트(예:
  로그인)에서는 nullable로 둔다.
- `dim_product`, `dim_user`는 Type 2 SCD. 자연키(`product_id`,
  `user_id`)로 속성 변경을 감지해서, 바뀌면 기존 행을
  `is_current=false`로 만료시키고 새 surrogate key로 새 행을 추가한다.
  `fact_events`는 적재 시점에 "현재(is_current=true) 버전"의
  surrogate key를 참조해, 그 거래 시점의 차원 값을 그대로 보존한다.
- `dim_date`는 속성이 바뀌지 않는 정적 참조 데이터라 SCD 적용 대상이
  아니다.
- 변환은 새 컴포넌트 없이 기존 Airflow `daily_etl` DAG을 확장해서
  수행한다. 변경 감지/만료 로직은 Python(DAG 태스크)에서 자연키
  기준으로 현재 버전과 비교하는 방식으로 구현한다.

## Consequences

- **좋아지는 점**: 퍼널(조회→장바구니→구매)과 매출을 같은 테이블로
  날짜/상품/사용자 임의 조합으로 분석 가능. 상품 가격이나 사용자
  속성이 바뀌어도 과거 거래를 왜곡 없이 재구성할 수 있음. ERD와
  SCD 처리 로직이 산출물로 남아 모델링 근거를 설명하기 좋음.
- **감수해야 하는 점**: Type 2 SCD는 변경 감지/만료 처리 로직이
  필요해 Type 1보다 구현·운영 복잡도가 높다. 차원 테이블에 속성이
  바뀔 때마다 새 행이 쌓여 테이블이 계속 커진다. 조회 시
  `is_current` 조건을 빠뜨리면 중복 집계될 위험이 있어, 뷰나 쿼리
  가이드로 보완이 필요하다.
- **후속 작업**: SCD 변경 감지 로직 단위 테스트 추가. 필요해지면
  `is_current` 필터를 강제하는 뷰(view)를 만들어 오용을 방지.

## Related

- Related ADRs: 없음
- Related Perfs: 없음
