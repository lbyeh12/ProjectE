import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchProduct, addToCart } from "../api/products";
import { trackEvent } from "../lib/tracker";
import { useAuth } from "../lib/store";

export function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const { userId } = useAuth();

  const { data: product, isLoading, isError } = useQuery({
    queryKey: ["product", productId],
    queryFn: () => fetchProduct(productId!),
    enabled: !!productId,
  });

  // 상세 페이지 진입 시 view 이벤트 기록 (상품 로드된 후)
  useEffect(() => {
    if (product) {
      trackEvent("view", {
        product_id: product.product_id,
        price: product.price,
      });
    }
  }, [product]);

  const handleAddToCart = async () => {
    if (!userId) {
      alert("장바구니에 담으려면 로그인이 필요합니다.");
      navigate("/login");
      return;
    }
    if (!product) return;

    try {
      await addToCart(userId, product.product_id);
      trackEvent("add_to_cart", {
        product_id: product.product_id,
        price: product.price,
      });
      alert("장바구니에 담았습니다.");
    } catch {
      alert("장바구니 담기에 실패했습니다.");
    }
  };

  if (isLoading) return <div className="container"><p className="muted">불러오는 중...</p></div>;
  if (isError || !product)
    return <div className="container"><div className="empty">상품을 찾을 수 없습니다.</div></div>;

  return (
    <div className="container">
      <button className="btn-ghost" onClick={() => navigate(-1)} style={{ padding: "0.4rem 0.9rem", marginBottom: "1.2rem" }}>
        ← 뒤로
      </button>
      <div className="detail">
        <div className="card-code">{product.product_id}</div>
        <h1>{product.description}</h1>
        <div className="price">£{product.price.toFixed(2)}</div>
        <p className="muted">지금까지 {product.total_purchase_count.toLocaleString()}회 구매되었습니다.</p>
        <button className="btn" onClick={handleAddToCart} style={{ marginTop: "1.4rem", padding: "0.7rem 1.4rem" }}>
          장바구니에 담기
        </button>
      </div>
    </div>
  );
}
