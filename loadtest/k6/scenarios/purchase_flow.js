// loadtest/k6/scenarios/purchase_flow.js
//
// 로그인 -> 상품 조회 -> 장바구니 담기 -> 구매까지의 전체 흐름.
// 인증이 필요한 엔드포인트(POST /cart, POST /purchase)가 부하 상황에서도
// 제대로 동작하는지, 그리고 JWT 검증 자체가 병목이 되진 않는지를 확인한다.
import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL } from "../lib/config.js";

/**
 * data: entry 스크립트의 setup() 이 반환한 { users: [...] } 를 받는다.
 * 준비된 테스트 계정이 없으면(시드 실패) 이 VU 이터레이션은 조용히 스킵한다.
 *
 * 계정은 "VU 번호로 고정 배정"이 아니라 "매 iteration마다 무작위로 선택"한다.
 * VU 고정 배정 방식은, 같은 VU가 이전 구매(장바구니 비우기)를 마치기 전에
 * 다음 iteration이 겹쳐 시작되면 "장바구니가 비어 있습니다"(400)가 나는
 * 레이스 컨디션이 있었다 (실제로 1차 부하 테스트에서 관찰됨,
 * docs/perf/001-baseline.md 참고). 무작위 선택 + 넉넉한 계정 수(VU 대비 여유)로
 * 같은 계정이 동시에 여러 iteration에서 쓰일 확률을 낮춘다.
 */
export function purchaseFlow(data) {
  const users = data && data.users ? data.users : [];
  if (users.length === 0) {
    sleep(1);
    return;
  }
  const user = users[Math.floor(Math.random() * users.length)];

  // 1. 로그인
  const loginRes = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ user_id: user.user_id, password: user.password }),
    { headers: { "Content-Type": "application/json" } }
  );
  const loginOk = check(loginRes, { "로그인 200": (r) => r.status === 200 });
  if (!loginOk) return;

  const token = JSON.parse(loginRes.body).access_token;
  const authHeaders = {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  };

  sleep(0.5);

  // 2. 상품 조회
  const listRes = http.get(`${BASE_URL}/products?limit=10`);
  let products = [];
  try {
    products = JSON.parse(listRes.body);
  } catch (e) {
    products = [];
  }
  if (products.length === 0) return;

  const product = products[Math.floor(Math.random() * products.length)];

  // 3. view 이벤트 (로그인 상태 -> 토큰의 user_id로 서버가 채움)
  http.post(
    `${BASE_URL}/events`,
    JSON.stringify({ event_type: "view", product_id: product.product_id, price: product.price }),
    authHeaders
  );

  sleep(Math.random() * 1.5 + 0.5);

  // 4. 장바구니 담기
  const cartRes = http.post(
    `${BASE_URL}/cart`,
    JSON.stringify({ product_id: product.product_id, quantity: 1 }),
    authHeaders
  );
  const cartOk = check(cartRes, { "장바구니 담기 200": (r) => r.status === 200 });
  if (!cartOk) return;

  sleep(Math.random() * 2 + 0.5); // 결제 고민하는 시간

  // 5. 구매
  const purchaseRes = http.post(`${BASE_URL}/purchase`, null, authHeaders);
  check(purchaseRes, { "구매 200": (r) => r.status === 200 });
}