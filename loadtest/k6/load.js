// loadtest/k6/load.js
//
// "대규모 트래픽" 의 1차 기준선(baseline)을 확인하는 부하 테스트.
// ADR 0002 의 잠정 성공 기준: VU 100, 5분 지속, 에러율 1% 미만, p95 500ms 미만.
//
// browse 시나리오에 더 많은 VU를 배분해서, 실제 이벤트 합성 비율
// (view:cart:purchase ≈ 10:3:1)에 가깝게 트래픽 구성을 맞춘다.
//
// 실행:
//   k6 run loadtest/k6/load.js
//   k6 run -e BASE_URL=http://localhost:8000 loadtest/k6/load.js
import { prepareTestUsers } from "./lib/setup.js";

export { browse } from "./scenarios/browse.js";
export { purchaseFlow } from "./scenarios/purchase_flow.js";

export const options = {
  // 회원가입(POST /auth/signup)이 순차적으로 여러 번 호출되고, 비밀번호
  // 해싱(bcrypt)이 의도적으로 느린 연산이라 기본 60초로는 타임아웃날 수 있다.
  // 넉넉하게 늘려둔다.
  setupTimeout: "120s",
  scenarios: {
    browse_traffic: {
      executor: "ramping-vus",
      exec: "browse",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 80 }, // 서서히 증가 (트래픽이 순간적으로 튀는 상황이 아니라 점진적 유입 가정)
        { duration: "3m", target: 80 }, // 목표 부하 유지
        { duration: "30s", target: 0 }, // 서서히 감소
      ],
    },
    purchase_traffic: {
      executor: "ramping-vus",
      exec: "purchaseFlow",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 },
        { duration: "3m", target: 20 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"], // 전체 에러율 1% 미만
    http_req_duration: ["p(95)<500"], // p95 응답시간 500ms 미만
  },
};

export function setup() {
  // purchase_traffic 시나리오의 최대 VU는 20이지만, 계정을 VU 수만큼만
  // 준비하면 같은 계정을 여러 iteration이 동시에 쓰다가 "장바구니가
  // 비었다"(400)는 레이스 컨디션이 생긴다 (1차 부하 테스트에서 실제로
  // 관찰됨: 21%가 이 이유로 실패). VU 수보다 넉넉하게 준비해서
  // 동시 충돌 확률을 낮춘다.
  return { users: prepareTestUsers(50) };
}