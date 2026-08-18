// loadtest/k6/inventory_race_light.js
//
// 시나리오 1: 물품 1개에 요청이 몰리는 경우 검증 (서버 부하 없음).
// adrs/0004-inventory-concurrency-control.md 의 핵심 주장인
// "재고보다 더 많이 팔리지 않는다"를 가장 단순한 조건에서 확인한다.
// VU 수를 적게(기본 10) 잡아서 부하 문제(docs/perf/002, 003)는 섞지 않고
// 순수하게 재고 정합성만 본다.
//
// 사전 준비/실행 방법/검증 절차는 loadtest/k6/README.md 참고.
import { prepareTestUsers } from "./lib/setup.js";

export { inventoryRace } from "./scenarios/inventory_race.js";

const VU_COUNT = parseInt(__ENV.VU_COUNT || "10", 10);

export const options = {
  scenarios: {
    inventory_race: {
      executor: "per-vu-iterations",
      exec: "inventoryRace",
      vus: VU_COUNT,
      // shared-iterations는 VU간 배분이 불균등해질 수 있어(어떤 VU는
      // 여러 번, 어떤 VU는 0번), "N명이 각자 정확히 1번씩"을 강제하려면
      // per-vu-iterations + iterations=1 이 필요하다.
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