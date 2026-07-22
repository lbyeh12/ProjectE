import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchProducts } from "../api/products";
import { trackEvent } from "../lib/tracker";
import type { Product } from "../types";

export function ProductsPage() {
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");

  const { data: products, isLoading, isError } = useQuery({
    queryKey: ["products", activeSearch],
    queryFn: () => fetchProducts({ limit: 40, search: activeSearch || undefined }),
  });

  const handleSearch = () => {
    setActiveSearch(search);
    // 검색 행동을 이벤트로 기록
    if (search.trim()) {
      trackEvent("search", { product_id: null });
    }
  };

  return (
    <div className="container">
      <div className="search-bar">
        <input
          type="text"
          placeholder="상품명으로 검색..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button className="btn" onClick={handleSearch}>
          검색
        </button>
      </div>

      {isLoading && <p className="muted">불러오는 중...</p>}
      {isError && (
        <div className="empty">
          상품을 불러오지 못했습니다. 백엔드 서버가 실행 중인지 확인하세요.
        </div>
      )}

      {products && products.length === 0 && (
        <div className="empty">검색 결과가 없습니다.</div>
      )}

      {products && products.length > 0 && (
        <div className="grid">
          {products.map((p) => (
            <ProductCard key={p.product_id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProductCard({ product }: { product: Product }) {
  return (
    <Link
      to={`/products/${product.product_id}`}
      className="card"
      onClick={() =>
        // 상품 클릭(=조회 의도)을 view 이벤트로 기록
        trackEvent("view", {
          product_id: product.product_id,
          price: product.price,
        })
      }
    >
      <div className="card-code">{product.product_id}</div>
      <div className="card-title">{product.description}</div>
      <div className="card-price">£{product.price.toFixed(2)}</div>
      <div className="card-meta">구매 {product.total_purchase_count.toLocaleString()}회</div>
    </Link>
  );
}
