// loadtest/k6/stress.js
//
// load.js 의 목표(VU 100)를 통과했다면, 그 이상으로 밀어붙여서
// "정확히 어디서부터 무너지는지"를 찾는 테스트. thresholds 를 abortOnFail 로
// 걸지 않는다 — 실패하는 지점을 보는 게 이 테스트의 목적이므로 중간에 멈추면 안 된다.
//
// 실행:
//   k6 run loadtest/k6/stress.js
import { prepareTestUsers } from "./lib/setup.js";

export { browse } from "./scenarios/browse.js";
export { purchaseFlow } from "./scenarios/purchase_flow.js";

export const options = {
  scenarios: {
    browse_traffic: {
      executor: "ramping-vus",
      exec: "browse",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 200 },
        { duration: "1m", target: 400 },
        { duration: "1m", target: 600 }, // load.js 목표(80)의 7~8배까지 밀어붙임
        { duration: "2m", target: 600 },
        { duration: "1m", target: 0 },
      ],
    },
    purchase_traffic: {
      executor: "ramping-vus",
      exec: "purchaseFlow",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 50 },
        { duration: "1m", target: 100 },
        { duration: "1m", target: 150 },
        { duration: "2m", target: 150 },
        { duration: "1m", target: 0 },
      ],
    },
  },
  // 여기서는 통과/실패를 가르기보다, 결과 리포트(p95/p99, 에러율 추이)를
  // 보고 "어느 VU 구간부터 무너지기 시작하는지"를 관찰하는 데 쓴다.
  thresholds: {
    http_req_failed: ["rate<0.50"], // 최소한의 안전장치 (50% 넘게 실패하면 조기 종료)
  },
};

export function setup() {
  return { users: prepareTestUsers(150) };
}
