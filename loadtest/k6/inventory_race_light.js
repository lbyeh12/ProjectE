// loadtest/k6/inventory_race_light.js
//
// 시나리오 1: 물품 1개에 요청이 몰리는 경우 검증 (서버 부하 없음).
// adrs/0004-inventory-concurrency-control.md 의 핵심 주장인
// "재고보다 더 많이 팔리지 않는다"를 가장 단순한 조건에서 확인한다.
//
// VU 수를 적게(기본 10) 잡아서, uvicorn 워커/DB 커넥션 풀이 부족해
// 생기는 부하 문제(docs/perf/002, 003)는 이 시나리오의 관심사가 아니다.
// 순수하게 "동시에 경쟁했을 때 재고 정합성이 지켜지는가"만 본다.
//
// 사전 준비:
//   1. 모든 사용자의 장바구니 정리 (이전 테스트 잔재 제거)
//      docker exec -i projecte-postgres psql -U postgres -d projecte \
//        < loadtest/k6/clear_all_carts.sql
//   2. 대상 상품의 재고를 정확한 값으로 세팅 (예: 재고 3개)
//      docker exec -i projecte-postgres psql -U postgres -d projecte \
//        -v product_id="'85123A'" -v stock=3 < loadtest/k6/setup_inventory_test.sql
//   3. 실행
//      k6 run -e PROJECT_ROOT=$(pwd) -e TARGET_PRODUCT_ID=85123A \
//        -e VU_COUNT=10 loadtest/k6/inventory_race_light.js
//
// 검증 방법: 실행 후 아래 쿼리로 확인한다.
//   SELECT stock FROM products WHERE product_id = '85123A';
//   -- 기대: 세팅한 재고 - 성공한 구매 건수 = 0 이상, 절대 음수가 아니어야 함
//   SELECT count(*) FROM raw_events
//   WHERE event_type='purchase' AND product_id='85123A';
//   -- 기대: 이 건수가 세팅했던 재고 수량을 절대 넘지 않아야 함 (초과 판매 방지 확인)
//
// k6 실행 결과 요약(터미널 출력)에서도 확인 가능:
//   purchase_success           : 성공 건수 (재고 수량과 같거나 그 이하여야 함)
//   purchase_rejected_409      : 재고부족 정상 거절 건수
//   purchase_connection_dropped: 반드시 0 이어야 함 (서버 정상 상황이므로)
//   purchase_server_error      : 반드시 0 이어야 함
import { prepareTestUsers } from "./lib/setup.js";

export { inventoryRace } from "./scenarios/inventory_race.js";

const VU_COUNT = parseInt(__ENV.VU_COUNT || "10", 10);

export const options = {
  scenarios: {
    inventory_race: {
      executor: "per-vu-iterations",
      exec: "inventoryRace",
      vus: VU_COUNT,
      // per-vu-iterations 는 "VU당 반복 횟수"를 의미하므로 1로 고정한다.
      // (shared-iterations를 썼을 때 "VU 10개가 전체 10번을 나눠 갖는다"는
      //  방식이라, 특정 VU가 여러 번 실행되고 다른 VU는 한 번도 실행 안
      //  되는 불균등 배분이 생겨 "10명이 각자 정확히 1번씩"이라는 이
      //  시나리오의 전제가 깨졌던 걸 확인했다. per-vu-iterations +
      //  iterations=1 로 VU당 정확히 1번을 강제한다.)
      iterations: 1,
      maxDuration: "1m",
    },
  },
  thresholds: {
    // 서버가 정상인 상황이라, 연결 끊김/서버 에러는 단 한 건도 없어야
    // 이 시나리오가 통과한 것이다. (장애를 의도적으로 안 주입했으니까)
    checks: ["rate==1.0"],
    purchase_connection_dropped: ["count==0"],
    purchase_server_error: ["count==0"],
  },
};

export function setup() {
  return { users: prepareTestUsers(VU_COUNT) };
}