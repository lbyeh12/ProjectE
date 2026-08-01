import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Header } from "./components/Header";
import { ProductsPage } from "./pages/ProductsPage";
import { ProductDetailPage } from "./pages/ProductDetailPage";
import { CartPage } from "./pages/CartPage";
import { LoginPage } from "./pages/LoginPage";
import { useAuth } from "./lib/store";

export function App() {
  const { restoreSession, isLoading } = useAuth();

  // 앱이 처음 뜰 때 저장된 토큰이 아직 유효한지 서버에 확인한다.
  // (새로고침해도 로그인 상태가 유지되도록)
  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  if (isLoading) {
    return null; // 세션 확인 중에는 잠깐 빈 화면 (깜빡임 방지)
  }

  return (
    <BrowserRouter>
      <Header />
      <Routes>
        <Route path="/" element={<ProductsPage />} />
        <Route path="/products/:productId" element={<ProductDetailPage />} />
        <Route path="/cart" element={<CartPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </BrowserRouter>
  );
}