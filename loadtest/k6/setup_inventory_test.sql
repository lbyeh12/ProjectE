-- loadtest/k6/setup_inventory_test.sql
--
-- 재고 경쟁 시나리오(scenarios/inventory_race.js) 실행 전, 테스트 대상
-- 상품 하나의 재고를 정확히 원하는 값으로 맞춰둔다.
-- (adrs/0004-inventory-concurrency-control.md 검증용)
--
-- 사용법:
--   docker exec -i projecte-postgres psql -U postgres -d projecte \
--     -v product_id="'85123A'" -v stock=10 -f loadtest/k6/setup_inventory_test.sql
--
-- 또는 값을 직접 바꿔서 psql에 붙여넣어도 된다.

UPDATE products
SET stock = :stock
WHERE product_id = :product_id;

-- 확인
SELECT product_id, description, price, stock
FROM products
WHERE product_id = :product_id;
