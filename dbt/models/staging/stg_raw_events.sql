-- raw_events 중 quarantine_events(adrs/0009)에 격리되지 않은 것만 통과시킨다.
-- raw_events 원본은 건드리지 않고(불변 원칙), 이 staging 뷰에서만 걸러낸다.
select
    re.id as source_event_id,
    re.user_id,
    re.event_type,
    re.product_id,
    re.price,
    re.timestamp
from {{ source('projecte', 'raw_events') }} re
where not exists (
    select 1 from {{ source('projecte', 'quarantine_events') }} qe
    where qe.source_event_id = re.id
)
