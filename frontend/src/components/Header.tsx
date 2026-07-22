import { Link } from "react-router-dom";
import { useAuth } from "../lib/store";

export function Header() {
  const { userId, logout } = useAuth();

  return (
    <header className="header">
      <div className="header-inner">
        <Link to="/" className="logo">
          ProjectE Shop
        </Link>
        <nav className="nav">
          <Link to="/">상품</Link>
          {userId ? (
            <>
              <Link to="/cart">장바구니</Link>
              <span className="muted">#{userId}</span>
              <button className="btn-ghost" onClick={logout} style={{ padding: "0.4rem 0.8rem" }}>
                로그아웃
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-ghost" style={{ padding: "0.4rem 0.8rem" }}>
              로그인
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
