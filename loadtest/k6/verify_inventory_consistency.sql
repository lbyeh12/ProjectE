-- loadtest/k6/verify_inventory_consistency.sql
--
-- inventory_race_crash.js(시나리오 2, 3) 실행 + chaos_kill_backend.sh로
-- 장애 주입 후, 데이터 정합성을 확인하는 쿼리 모음.
--
-- 실행 전 :product_id 를 실제 테스트에 쓴 상품으로, :initial_stock 을
-- setup_inventory_test.sql 로 세팅했던 재고값으로 바꿔서 사용한다.
--
--   docker exec -i projecte-postgres psql -U postgres -d projecte \
--     -v product_id="'85123A'" -v initial_stock=5 \
--     -f loadtest/k6/verify_inventory_consistency.sql


-- ============================================================
-- 시나리오 2 대상: DB(재고/주문) 자체의 정합성
-- "처리 도중 backend가 죽어도, DB 트랜잭션의 원자성이 지켜졌는가"
-- ============================================================

-- 2-1. 현재 재고. 절대 음수가 아니어야 하고, 정확히
--      (초기 재고 - 성공한 구매 건수) 여야 한다.
SELECT
    product_id,
    stock AS current_stock,
    :initial_stock AS initial_stock,
    (:initial_stock - stock) AS stock_decreased_by
FROM products
WHERE product_id = :product_id;

-- 2-2. 이 상품에 대해 실제로 커밋까지 완료된 구매가 몇 건인지.
--      raw_events 는 Kafka -> Spark 를 거쳐 쌓이므로, 이 값은 사실
--      "DB에 반영된 결과"가 아니라 "Kafka로 전송된 이벤트 수"에 더
--      가깝다 (checkout()에서 Kafka 전송이 db.commit() 이전에 일어나기
--      때문 - 시나리오 3에서 이 차이 자체를 검증 대상으로 삼는다).
--      시나리오 2 관점에서는 우선 "재고 차감량과 대략 맞는지" 정도의
--      1차 확인으로 참고한다.
SELECT count(*) AS purchase_event_count
FROM raw_events
WHERE event_type = 'purchase' AND product_id = :product_id;

-- 2-3. 장애 발생 시점 전후로 "idle in transaction" 상태로 남은 세션이
--      있는지 확인. backend가 kill되면 그 연결이 물고 있던 트랜잭션은
--      PostgreSQL이 자동으로 정리(rollback)해야 한다. 이 쿼리 결과가
--      비어있어야 "제대로 정리됐다"는 뜻이다. 만약 남아있다면, 락이
--      해제되지 않고 방치되어 있다는 위험 신호다.
SELECT pid, state, query, now() - state_change AS idle_duration
FROM pg_stat_activity
WHERE datname = 'projecte' AND state = 'idle in transaction'
ORDER BY state_change;

-- 2-4. 종합 판정: 성공한 구매 건수가 초기 재고를 넘지 않았는가
--      (초과 판매 여부의 최종 확인). true 가 나와야 통과.
SELECT
    (:initial_stock - stock) <= :initial_stock AS no_overselling,
    stock >= 0 AS stock_non_negative
FROM products
WHERE product_id = :product_id;


-- ============================================================
-- 시나리오 3 대상: DB와 Kafka(-> Spark -> raw_events/product_stats)
-- 사이의 정합성. "이중 쓰기 문제"가 실제로 재현되는지 확인.
-- ============================================================

-- 3-1. DB 기준 판매량(재고 감소분)과, Kafka를 거쳐 Spark가 집계한
--      product_stats 의 구매 수를 나란히 비교한다.
--      checkout()의 현재 구현은 Kafka 전송을 db.commit() "이전"에
--      하므로, 이론적으로 두 가지 불일치가 모두 가능하다:
--        (a) Kafka 전송 성공 후 commit 전에 서버가 죽음
--            -> product_stats 에는 구매가 잡혔는데 실제 DB 재고는
--               안 줄어든 상태 (product_stats 쪼이 더 큼)
--        (b) 반대로 commit은 됐는데 Kafka 전송이 유실됨
--            -> DB 재고는 줄었는데 product_stats에는 안 잡힘
--               (product_stats 가 더 작음)
--      아래 두 값이 정확히 일치해야 "정합성이 지켜졌다"고 볼 수 있다.
SELECT
    (:initial_stock - p.stock) AS db_based_purchase_count,
    COALESCE(ps.purchase_count, 0) AS kafka_based_purchase_count,
    (:initial_stock - p.stock) - COALESCE(ps.purchase_count, 0) AS mismatch
FROM products p
LEFT JOIN product_stats ps ON ps.product_id = p.product_id
WHERE p.product_id = :product_id;

-- 3-2. raw_events 에 남은 purchase 이벤트 수와도 비교 (product_stats가
--      집계 테이블이라면, raw_events는 원본에 더 가까움 - 둘 다 확인).
SELECT
    (:initial_stock - p.stock) AS db_based_purchase_count,
    (
        SELECT count(*) FROM raw_events
        WHERE event_type = 'purchase' AND product_id = :product_id
    ) AS raw_events_purchase_count
FROM products p
WHERE p.product_id = :product_id;

-- 3-3. 장애 시점에 장바구니에 남아있는 항목이 있는지 확인.
--      checkout()이 재고 검증에 통과했지만 커밋 전에 죽었다면, 그
--      트랜잭션 전체가 롤백되므로 장바구니 항목도 삭제되지 않은 채
--      남아있어야 한다 (원자성이 지켜졌다면). 만약 재고는 안 줄었는데
--      장바구니도 이미 비어있다면, 커밋 순서상 이상한 상태이므로
--      점검이 필요하다.
SELECT ci.user_id, ci.product_id, ci.quantity, ci.added_at
FROM cart_items ci
WHERE ci.product_id = :product_id;
