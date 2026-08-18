{{
  config(
    materialized='incremental',
    unique_key='event_key'
  )
}}

-- fact_events 그레인: stg_raw_events(=raw_events - 격리분) 1건당 1행.
-- (adrs/0008 참고) event_type이 view/search/purchase 등일 때 전부
-- 이 테이블에 담기고, revenue는 purchase일 때만 값을 가진다.
--
-- incremental: 이미 적재된 source_event_id는 재처리하지 않는다(Fact는
-- 한 번 확정되면 안 바뀌는 값이라, dim처럼 "현재 버전 갱신" 개념이
-- 없다 - 그래서 dim_product/dim_user와 달리 만료 로직이 필요 없다).

with events as (
    select * from {{ ref('stg_raw_events') }}
    {% if is_incremental() %}
    where source_event_id not in (select source_event_id from {{ this }})
    {% endif %}
),

dim_product_current as (
    select * from {{ ref('dim_product') }} where is_current
),

dim_user_current as (
    select * from {{ ref('dim_user') }} where is_current
)

select
    {{ dbt_utils.generate_surrogate_key(['e.source_event_id']) }} as event_key,
    d.date_key,
    dp.product_key,
    du.user_key,
    e.event_type,
    e.price,
    case when e.event_type = 'purchase' then coalesce(e.price, 0) else 0 end as revenue,
    e.source_event_id
from events e
left join {{ ref('dim_date') }} d
    on d.date_key = to_char(e.timestamp::date, 'YYYYMMDD')::int
left join dim_product_current dp on dp.product_id = e.product_id
left join dim_user_current du on du.user_id = e.user_id
