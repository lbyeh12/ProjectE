// loadtest/k6/smoke.js
//
// 스모크 테스트: 본격적인 부하를 걸기 전에, 시나리오 스크립트 자체가
// 문법적으로/논리적으로 문제없이 API를 호출하는지 최소한으로 확인한다.
// VU 1개, 짧은 시간만 돈다. 이게 실패하면 load.js/stress.js 는 시도할 필요도 없다.
//
// 실행:
//   k6 run loadtest/k6/smoke.js
//   k6 run -e BASE_URL=http://localhost:8000 loadtest/k6/smoke.js
import { sleep } from "k6";
import { browse } from "./scenarios/browse.js";
import { purchaseFlow } from "./scenarios/purchase_flow.js";
import { prepareTestUsers } from "./lib/setup.js";

export const options = {
  vus: 1,
  iterations: 5,
  thresholds: {
    http_req_failed: ["rate==0"], // 스모크 단계에서는 실패가 하나도 없어야 함
  },
};

export function setup() {
  return { users: prepareTestUsers(3) };
}

export default function (data) {
  browse();
  sleep(1);
  purchaseFlow(data);
  sleep(1);
}
