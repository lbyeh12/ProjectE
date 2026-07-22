import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchCart, fetchProduct, removeFromCart, checkout } from "../api/products";
import { useAuth } from "../lib/store";
import { useEffect, useState } from "react";
import type { CartItem, Product } from "../types";

export function CartPage() {
  const { userId } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: cartItems, isLoading } = useQuery({
    queryKey: ["cart", userId],
    queryFn: () => fetchCart(userId!),
    enabled: !!userId,
  });

  // 장바구니 항목의 상품 정보(가격/이름)를 함께 로드
  const [productMap, setProductMap] = useState<Record<string, Product>>({});

  useEffect(() => {
    if (!cartItems) return;
    Promise.all(
      cartItems.map((item) => fetchProduct(item.product_id).catch(() => null))
    ).then((products) => {
      const map: Record<string, Product> = {};
      products.forEach((p) => {
        if (p) map[p.product_id] = p;
      });
      setProductMap(map);
    });
  }, [cartItems]);

  if (!userId) {
    return (
      <div className="container">
        <div className="empty">
          로그인 후 장바구니를 확인할 수 있습니다.
          <br />
          <button className="btn" onClick={() => navigate("/login")} style={{ marginTop: "1rem" }}>
            로그인하러 가기
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) return <div className="container"><p className="muted">불러오는 중...</p></div>;

  const items = cartItems ?? [];
  const total = items.reduce((sum, item) => {
    const price = productMap[item.product_id]?.price ?? 0;
    return sum + price * item.quantity;
  }, 0);

  const handleRemove = async (item: CartItem) => {
    await removeFromCart(userId, item.product_id);
    queryClient.invalidateQueries({ queryKey: ["cart", userId] });
  };

  const handleCheckout = async () => {
    if (items.length === 0) return;
    try {
      const result = await checkout(userId);
      // 구매 완료 이벤트는 백엔드 /purchase 가 각 상품별로 이미 기록하므로
      // 여기서는 중복 기록하지 않는다.
      alert(`구매 완료! ${result.purchased_items}종 / £${result.total_price.toFixed(2)}`);
      queryClient.invalidateQueries({ queryKey: ["cart", userId] });
      navigate("/");
    } catch {
      alert("구매 처리에 실패했습니다.");
    }
  };

  return (
    <div className="container">
      <h1 style={{ fontSize: "1.4rem", marginBottom: "1.4rem" }}>장바구니</h1>

      {items.length === 0 ? (
        <div className="empty">장바구니가 비어 있습니다.</div>
      ) : (
        <>
          {items.map((item) => {
            const product = productMap[item.product_id];
            return (
              <div key={item.id} className="cart-row">
                <div>
                  <div style={{ fontWeight: 500 }}>{product?.description ?? item.product_id}</div>
                  <div className="card-code">
                    {item.product_id} · 수량 {item.quantity}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                  <span style={{ fontWeight: 700 }}>
                    £{((product?.price ?? 0) * item.quantity).toFixed(2)}
                  </span>
                  <button className="btn-danger" onClick={() => handleRemove(item)}>
                    삭제
                  </button>
                </div>
              </div>
            );
          })}

          <div className="cart-total">
            <span>합계</span>
            <span>£{total.toFixed(2)}</span>
          </div>

          <button
            className="btn"
            onClick={handleCheckout}
            style={{ width: "100%", marginTop: "1.4rem", padding: "0.8rem" }}
          >
            구매하기
          </button>
        </>
      )}
    </div>
  );
}
