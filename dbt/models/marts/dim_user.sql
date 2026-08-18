{{
  config(
    materialized='incremental',
    unique_key='user_key',
    on_schema_change='fail'
  )
}}

-- dim_product.sql과 동일한 SCD Type 2 패턴. 상세 설명은 그쪽 주석 참고.

with source_users as (
    select user_id, country
    from {{ source('projecte', 'users') }}
)

{% if is_incremental() %}

, current_dim as (
    select * from {{ this }} where is_current
)

, changed as (
    select s.user_id, s.country
    from source_users s
    left join current_dim c on c.user_id = s.user_id
    where c.user_id is null
       or c.country is distinct from s.country
)

, new_versions as (
    select
        {{ dbt_utils.generate_surrogate_key(['user_id', 'country', 'current_timestamp']) }} as user_key,
        user_id,
        country,
        cast(current_timestamp as timestamp) as effective_date,
        cast(null as timestamp) as expiration_date,
        true as is_current
    from changed
)

, expired_versions as (
    select
        c.user_key,
        c.user_id,
        c.country,
        c.effective_date,
        cast(current_timestamp as timestamp) as expiration_date,
        false as is_current
    from current_dim c
    inner join changed ch on ch.user_id = c.user_id
)

select * from new_versions
union all
select * from expired_versions

{% else %}

select
    {{ dbt_utils.generate_surrogate_key(['user_id', 'country', 'current_timestamp']) }} as user_key,
    user_id,
    country,
    cast(current_timestamp as timestamp) as effective_date,
    cast(null as timestamp) as expiration_date,
    true as is_current
from source_users

{% endif %}