// 백엔드 app/schemas.py 와 일치하는 타입 정의

export interface Product {
  product_id: string;
  description: string;
  price: number;
  total_purchase_count: number;
}

export interface CartItem {
  id: number;
  user_id: number;
  product_id: string;
  quantity: number;
  added_at: string;
}

// 백엔드 EventType 과 동일한 7종
export type EventType =
  | "view"
  | "search"
  | "add_to_cart"
  | "purchase"
  | "refund"
  | "signup"
  | "login";

export interface EventPayload {
  user_id?: number | null;
  event_type: EventType;
  product_id?: string | null;
  price?: number | null;
  timestamp?: string | null;
}

export interface PurchaseResult {
  user_id: number;
  purchased_items: number;
  total_price: number;
}
