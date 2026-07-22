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

export async function addToCart(
  userId: number,
  productId: string,
  quantity = 1
): Promise<CartItem> {
  const res = await apiClient.post<CartItem>("/cart", {
    user_id: userId,
    product_id: productId,
    quantity,
  });
  return res.data;
}

export async function fetchCart(userId: number): Promise<CartItem[]> {
  const res = await apiClient.get<CartItem[]>(`/cart/${userId}`);
  return res.data;
}

export async function removeFromCart(
  userId: number,
  productId: string
): Promise<void> {
  await apiClient.delete(`/cart/${userId}/${productId}`);
}

export async function checkout(userId: number): Promise<PurchaseResult> {
  const res = await apiClient.post<PurchaseResult>("/purchase", {
    user_id: userId,
  });
  return res.data;
}
