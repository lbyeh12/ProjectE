{{
  config(
    materialized='incremental',
    unique_key='product_key',
    on_schema_change='fail'
  )
}}

-- effective_date/expiration_date는 timestamp로 명시 캐스팅한다.
-- current_timestamp가 PostgreSQL 기본으로 timestamptz(타임존 포함)를
-- 반환하는데, 최초 생성 시(else 분기, cast(null as timestamp))와
-- 타입이 안 맞아 "source/target schema out of sync" 에러가 났었다.

-- SCD Type 2 (adrs/0008): 상품 속성이 바뀌면 기존 행을 만료시키고
-- 새 surrogate key로 새 행을 추가한다.
--
-- dbt의 incremental merge는 "결과셋에 있는 product_key와 기존 테이블의
-- product_key가 같으면 UPDATE, 없으면 INSERT" 방식이다. 그래서 이
-- SELECT는 두 종류의 행을 함께 내보낸다:
--   1. new_versions : 새 product_key (INSERT됨)
--   2. expired_versions : 기존 product_key 그대로, is_current만
--      false로 바꾼 행 (기존 행과 매칭되어 UPDATE됨)
-- 이렇게 안 하면 새 버전만 계속 추가되고 옛 버전이 영원히
-- is_current=true로 남는 버그가 생긴다.

with source_products as (
    select product_id, description, price
    from {{ source('projecte', 'products') }}
)

{% if is_incremental() %}

, current_dim as (
    select * from {{ this }} where is_current
)

, changed as (
    select s.product_id, s.description, s.price
    from source_products s
    left join current_dim c on c.product_id = s.product_id
    where c.product_id is null
       or c.description is distinct from s.description
       or c.price is distinct from s.price
)

, new_versions as (
    select
        {{ dbt_utils.generate_surrogate_key(['product_id', 'description', 'price', 'current_timestamp']) }} as product_key,
        product_id,
        description,
        price,
        cast(current_timestamp as timestamp) as effective_date,
        cast(null as timestamp) as expiration_date,
        true as is_current
    from changed
)

, expired_versions as (
    select
        c.product_key,
        c.product_id,
        c.description,
        c.price,
        c.effective_date,
        cast(current_timestamp as timestamp) as expiration_date,
        false as is_current
    from current_dim c
    inner join changed ch on ch.product_id = c.product_id
)

select * from new_versions
union all
select * from expired_versions

{% else %}

-- 최초 실행(테이블이 아직 없음): 전체를 신규 버전으로 적재
select
    {{ dbt_utils.generate_surrogate_key(['product_id', 'description', 'price', 'current_timestamp']) }} as product_key,
    product_id,
    description,
    price,
    cast(current_timestamp as timestamp) as effective_date,
    cast(null as timestamp) as expiration_date,
    true as is_current
from source_products

{% endif %}