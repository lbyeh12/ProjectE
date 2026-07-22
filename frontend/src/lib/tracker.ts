import { apiClient } from "../api/client";
import type { EventType, EventPayload } from "../types";

/**
 * 사용자 행동 이벤트 추적 레이어.
 *
 * 이 프로젝트의 핵심 설계 지점이다.
 * 모든 사용자 행동(페이지 조회, 상품 클릭, 장바구니 담기 등)은 반드시 이
 * trackEvent() 함수 하나만 거쳐서 서버로 전송된다.
 *
 * 지금은 POST /events (FastAPI -> PostgreSQL 직접 저장) 로 보내지만,
 * 이후 Kafka 도입 단계에서 백엔드 /events 엔드포인트 내부 구현만
 * Kafka Producer 로 교체하면 되고, 이 프론트엔드 코드는 전혀 바꿀 필요가 없다.
 *
 * 실패해도 사용자 경험을 막지 않도록 fire-and-forget 방식으로 보낸다.
 */
export function trackEvent(
  eventType: EventType,
  payload: Omit<EventPayload, "event_type"> = {}
): void {
  const event: EventPayload = {
    event_type: eventType,
    user_id: payload.user_id ?? getCurrentUserId(),
    product_id: payload.product_id ?? null,
    price: payload.price ?? null,
    // timestamp 는 서버에서 채우므로 생략
  };

  // 응답을 기다리지 않고 보낸다 (트래킹이 UI를 막으면 안 됨)
  apiClient.post("/events", event).catch((err) => {
    // 트래킹 실패는 콘솔에만 남기고 조용히 넘어간다.
    console.warn("[tracker] 이벤트 전송 실패:", eventType, err?.message);
  });
}

/**
 * 현재 로그인한 사용자 ID.
 * 아직 실제 인증이 없으므로, 데모용으로 로컬에 저장된 user_id를 쓴다.
 * (로그인 페이지에서 setCurrentUserId 로 설정)
 */
const USER_ID_KEY = "projecte_user_id";

export function getCurrentUserId(): number | null {
  const raw = sessionStorage.getItem(USER_ID_KEY);
  return raw ? Number(raw) : null;
}

export function setCurrentUserId(userId: number): void {
  sessionStorage.setItem(USER_ID_KEY, String(userId));
}

export function clearCurrentUserId(): void {
  sessionStorage.removeItem(USER_ID_KEY);
}
