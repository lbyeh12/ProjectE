// loadtest/k6/scenarios/inventory_race.js
//
// adrs/0004-inventory-concurrency-control.md 검증용 시나리오.
// browse.js/purchase_flow.js 는 "여러 상품에 흩어지는 일반적인 트래픽"을
// 재현하지만, 이 시나리오는 반대로 "모든 VU가 정확히 같은 상품 하나"를
// 노리게 만든다. 재고 경쟁(동시성 문제)을 의도적으로 발생시키는 게 목적이다.
//
// 실행 전 반드시 setup_inventory_test.sql 로 대상 상품의 재고를 원하는
// 값으로 맞춰둬야 한다 (그래야 "재고 N개에 M명이 몰렸을 때" 라는
// 조건을 정확히 재현할 수 있다).
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL } from "../lib/config.js";

// 테스트 대상 상품. 환경변수로 지정하고, 없으면 흔한 UCI 데이터셋
// 상품 코드를 기본값으로 둔다 (반드시 setup_inventory_test.sql 로 재고를
// 세팅할 때 쓴 상품과 같아야 한다).
export const TARGET_PRODUCT_ID = __ENV.TARGET_PRODUCT_ID || "85123A";

// 구매 결과를 종류별로 정확히 세기 위한 커스텀 카운터.
// k6의 기본 check()만 쓰면 네트워크 레벨 장애(연결 끊김/타임아웃)일 때
// r.status가 0이 되는데, `status < 500` 같은 조건은 0도 참이 되어
// "성공"으로 잘못 집계된다. 장애 주입 시나리오(2, 3번)에서는 이 구간이
// 핵심 관찰 대상이라 명확하게 분리된 카운터로 추적한다.
export const purchaseSuccess = new Counter("purchase_success");        // 200
export const purchaseRejected = new Counter("purchase_rejected_409");  // 409, 재고부족 정상 거절
export const purchaseServerError = new Counter("purchase_server_error"); // 5xx, 서버가 응답은 했지만 에러
export const purchaseConnectionDropped = new Counter("purchase_connection_dropped"); // 0, 연결 자체가 끊김 (장애 상황의 핵심 신호)
// 200/409/5xx/0 어디에도 안 걸리는 "그 외" 상태(400, 401, 404 등).
// 놓치지 않도록 카운터로 잡고, body도 같이 로그로 남긴다.
export const purchaseUnexpectedStatus = new Counter("purchase_unexpected_status");

/**
 * data: entry 스크립트의 setup() 이 반환한 { users: [...] } 를 받는다.
 * 모든 VU가 정확히 같은 상품(TARGET_PRODUCT_ID) 하나만 담아 구매를 시도한다.
 */
export function inventoryRace(data) {
  const users = data && data.users ? data.users : [];
  if (users.length === 0) {
    sleep(0.5);
    return;
  }
  // "서로 다른 N명이 재고를 동시에 노리는" 상황을 재현하려는 목적이라,
  // 계정을 무작위로 뽑으면 같은 계정이 여러 VU에 겹쳐 뽑힐 수 있다
  // (겹치면 한쪽이 빈 장바구니로 구매를 시도해 400이 난다). VU 번호로
  // 계정을 고정 배정해서 정확히 "VU 수만큼의 서로 다른 사람"이 경쟁하게
  // 한다. (다른 시나리오는 반대로 무작위 선택을 쓴다 — 목적이 다르다.)
  const user = users[(__VU - 1) % users.length];

  // 1. 로그인
  const loginRes = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ user_id: user.user_id, password: user.password }),
    { headers: { "Content-Type": "application/json" } }
  );
  if (loginRes.status !== 200) return;
  const token = JSON.parse(loginRes.body).access_token;
  const authHeaders = {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  };

  // 2. 오직 타겟 상품만, 정확히 수량 1로 장바구니에 담는다.
  //    장바구니 초기화는 스크립트 흐름과 분리해 테스트 실행 "전에"
  //    clear_all_carts.sql 로 한 번에 처리한다 (README 참고).
  const cartRes = http.post(
    `${BASE_URL}/cart`,
    JSON.stringify({ product_id: TARGET_PRODUCT_ID, quantity: 1 }),
    authHeaders
  );
  if (cartRes.status !== 200) {
    // 조용히 return 하면 결과 집계 어디에도 안 남으므로 반드시 로그로 남긴다.
    console.warn(
      `[inventory_race] 장바구니 담기 실패: status=${cartRes.status} body=${cartRes.body}`
    );
    return;
  }

  // 3. 구매 시도. 여기서 나오는 결과가 이 시나리오의 핵심 관찰 대상이다.
  //    - 200: 구매 성공 (재고를 확보한 사용자)
  //    - 409: 재고 부족으로 정상 거절 (adrs/0004 에서 의도한 동작),
  //           또는 같은 멱등성 키로 처리 중인 요청과 겹침 (adrs/0006)
  //    - 5xx: 서버가 응답은 했지만 처리 중 에러 (코드 예외 등)
  //    - 0  : 연결 자체가 끊김 (backend가 죽거나 네트워크 단절 - 장애 시나리오의 핵심 신호)
  //    - 그 외: 예상 못 한 상태 (400/401/404 등) - 반드시 카운터+로그로 남김
  //
  // Idempotency-Key: 이 VU, 이 iteration에 대해 고유한 키를 만들어
  // 붙인다 (adrs/0006-idempotency-store-selection.md). 실제 재시도
  // 상황(같은 키로 다시 요청)은 이 시나리오가 아니라 별도로 검증한다 -
  // 여기서는 "멱등성 키를 붙여도 정상 흐름이 깨지지 않는지"를 확인한다.
  const idempotencyKey = `${__VU}-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
  const purchaseHeaders = {
    headers: { ...authHeaders.headers, "Idempotency-Key": idempotencyKey },
  };
  const purchaseRes = http.post(`${BASE_URL}/purchase`, null, purchaseHeaders);

  if (purchaseRes.status === 200) {
    purchaseSuccess.add(1);
  } else if (purchaseRes.status === 409) {
    purchaseRejected.add(1);
  } else if (purchaseRes.status === 0) {
    purchaseConnectionDropped.add(1);
  } else if (purchaseRes.status >= 500) {
    purchaseServerError.add(1);
  } else {
    // 200/409/5xx/0 어디에도 안 걸리는 케이스. 조용히 사라지게 두지 않고
    // 반드시 카운터로 잡고, 실제 에러 내용을 로그로 남긴다.
    purchaseUnexpectedStatus.add(1);
    console.warn(
      `[inventory_race] 예상 못 한 구매 응답: status=${purchaseRes.status} body=${purchaseRes.body}`
    );
  }

  // 시나리오 1(서버 정상)에서는 이 체크가 100% 통과해야 한다.
  // 시나리오 2/3(장애 주입)에서는 이 체크가 실패하는 게 오히려 "의도대로
  // 장애가 재현됐다"는 신호이므로, 실행 스크립트(inventory_race_crash.js)
  // 쪽에서는 이 threshold를 강제하지 않는다.
  check(purchaseRes, {
    "구매 성공(200) 또는 재고부족 정상거절(409)": (r) =>
      r.status === 200 || r.status === 409,
  });
}