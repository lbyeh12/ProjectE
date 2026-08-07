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
  // 300명 회원가입을 순차 처리해야 해서 시간이 꽤 걸린다 (bcrypt 해싱 포함).
  // 넉넉하게 잡는다.
  setupTimeout: "300s",
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
  // purchase_traffic 최대 VU(150)의 2배로 계정을 준비해서, 서로 다른
  // iteration이 같은 계정을 동시에 쓸 확률을 낮춘다 (완전히 0으로
  //만들지는 않음 — 실제 서비스에서도 계정 충돌은 낮은 확률로 있을 수
  // 있는 정상적인 엣지 케이스이므로, 노이즈를 "충분히 낮추는" 것을
  // 목표로 한다. docs/perf/001-baseline.md 참고).
  return { users: prepareTestUsers(300) };
}