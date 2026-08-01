import { apiClient } from "./client";
import type { Product, CartItem, PurchaseResult } from "../types";

export async function fetchProducts(params?: {
  skip?: number;
  limit?: number;
  search?: string;
}): Promise<Product[]> {
  const res = await apiClient.get<Product[]>("/products", { params });
  return res.data;
}

export async function fetchProduct(productId: string): Promise<Product> {
  const res = await apiClient.get<Product>(`/products/${productId}`);
  return res.data;
}

// user_id는 더 이상 클라이언트가 지정하지 않는다. 로그인 토큰으로 서버가 식별한다.
// (로그인 안 된 상태로 호출하면 백엔드가 401을 응답한다)

export async function addToCart(productId: string, quantity = 1): Promise<CartItem> {
  const res = await apiClient.post<CartItem>("/cart", {
    product_id: productId,
    quantity,
  });
  return res.data;
}

export async function fetchCart(): Promise<CartItem[]> {
  const res = await apiClient.get<CartItem[]>("/cart");
  return res.data;
}

export async function removeFromCart(productId: string): Promise<void> {
  await apiClient.delete(`/cart/${productId}`);
}

export async function checkout(): Promise<PurchaseResult> {
  const res = await apiClient.post<PurchaseResult>("/purchase");
  return res.data;
}