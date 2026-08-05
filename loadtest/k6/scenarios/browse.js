// loadtest/k6/scenarios/browse.js
//
// 실제 트래픽의 대부분을 차지하는 패턴: 비로그인 상태로 상품을 둘러보는 흐름.
// 데이터셋 이벤트 합성 시 정한 비율(view:cart:purchase ≈ 10:3:1)을 그대로
// 반영해서, 이 시나리오가 purchase_flow보다 훨씬 많은 VU를 담당하게 한다
// (실제 배분은 각 엔트리 스크립트의 options.scenarios 에서 조정).
import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL } from "../lib/config.js";

export function browse() {
  // 1. 상품 목록 조회 (검색 없이)
  const listRes = http.get(`${BASE_URL}/products?limit=20`);
  check(listRes, {
    "상품 목록 200": (r) => r.status === 200,
  });

  let products = [];
  try {
    products = JSON.parse(listRes.body);
  } catch (e) {
    products = [];
  }

  sleep(Math.random() * 2 + 0.5); // 사용자가 목록을 훑어보는 시간

  if (products.length === 0) {
    return; // 상품이 하나도 없으면(DB 미적재) 나머지 단계는 스킵
  }

  const product = products[Math.floor(Math.random() * products.length)];

  // 2. 가끔 검색도 한다 (검색 이벤트 발생 비중을 위해)
  if (Math.random() < 0.2) {
    const searchRes = http.get(
      `${BASE_URL}/products?search=${encodeURIComponent(product.description.split(" ")[0])}`
    );
    check(searchRes, { "검색 200": (r) => r.status === 200 });
    http.post(
      `${BASE_URL}/events`,
      JSON.stringify({ event_type: "search" }),
      { headers: { "Content-Type": "application/json" } }
    );
  }

  // 3. 상품 상세 조회
  const detailRes = http.get(`${BASE_URL}/products/${product.product_id}`);
  check(detailRes, { "상품 상세 200": (r) => r.status === 200 });

  sleep(Math.random() * 2 + 0.5);

  // 4. view 이벤트 기록 (비로그인이므로 user_id 없이 전송, 실제 프론트의
  //    trackEvent() 와 동일한 요청 형식)
  const eventRes = http.post(
    `${BASE_URL}/events`,
    JSON.stringify({
      event_type: "view",
      product_id: product.product_id,
      price: product.price,
    }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(eventRes, { "view 이벤트 200": (r) => r.status === 200 });

  sleep(Math.random() * 1.5);
}
