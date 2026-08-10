-- loadtest/k6/clear_all_carts.sql
--
-- 모든 사용자의 장바구니를 비운다.
-- 재고 경쟁 시나리오(inventory_race_light.js 등)를 실행하기 전에,
-- 이전 테스트에서 남은 장바구니 항목이 검증 결과를 오염시키는 걸
-- 방지하기 위해 사용한다 (예: 이전 실행에서 구매 거절되어 남은 항목이
-- 이번 실행의 "장바구니가 비어 있어야 정상"이라는 전제를 깨는 문제).
--
-- 사용법:
--   docker exec -i projecte-postgres psql -U postgres -d projecte \
--     < loadtest/k6/clear_all_carts.sql

DELETE FROM cart_items;

-- 확인 (0이어야 정상)
SELECT count(*) AS remaining_cart_items FROM cart_items;
