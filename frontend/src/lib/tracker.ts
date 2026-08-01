import { apiClient } from "../api/client";
import type { EventType, EventPayload } from "../types";

/**
 * 사용자 행동 이벤트 추적 레이어.
 *
 * 이 프로젝트의 핵심 설계 지점이다.
 * 모든 사용자 행동(페이지 조회, 상품 클릭, 장바구니 담기 등)은 반드시 이
 * trackEvent() 함수 하나만 거쳐서 서버로 전송된다.
 *
 * user_id는 더 이상 여기서 직접 넣지 않는다. 로그인 상태라면 client.ts의
 * axios 인터셉터가 Authorization 헤더로 토큰을 실어 보내고, 백엔드가
 * 그 토큰에서 user_id를 추출해 덮어쓴다 (비로그인이면 user_id 없이 전송됨).
 *
 * 실패해도 사용자 경험을 막지 않도록 fire-and-forget 방식으로 보낸다.
 */
export function trackEvent(
  eventType: EventType,
  payload: Omit<EventPayload, "event_type" | "user_id"> = {}
): void {
  const event: EventPayload = {
    event_type: eventType,
    product_id: payload.product_id ?? null,
    price: payload.price ?? null,
    // timestamp 는 서버에서 채우므로 생략
    // user_id는 보내지 않는다 (로그인 상태면 서버가 토큰에서 채움)
  };

  // 응답을 기다리지 않고 보낸다 (트래킹이 UI를 막으면 안 됨)
  apiClient.post("/events", event).catch((err) => {
    // 트래킹 실패는 콘솔에만 남기고 조용히 넘어간다.
    console.warn("[tracker] 이벤트 전송 실패:", eventType, err?.message);
  });
}