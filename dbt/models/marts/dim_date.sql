-- stg_raw_events에 등장한 날짜들로 dim_date를 채운다.
-- dim_date는 SCD 대상이 아니다(정적 참조 데이터, adrs/0008 참고).
with distinct_dates as (
    select distinct timestamp::date as full_date
    from {{ ref('stg_raw_events') }}
)

select
    to_char(full_date, 'YYYYMMDD')::int as date_key,
    full_date,
    extract(year from full_date)::int as year,
    extract(month from full_date)::int as month,
    extract(day from full_date)::int as day,
    extract(isodow from full_date)::int as day_of_week,
    extract(isodow from full_date)::int in (6, 7) as is_weekend
from distinct_dates
