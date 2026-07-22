import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/store";
import { trackEvent } from "../lib/tracker";

/**
 * 로그인 페이지.
 *
 * 실제 인증 시스템은 아직 없다. 이 데모에서는 데이터셋에 존재하는 CustomerID를
 * 그대로 입력받아 "그 사용자로 로그인"하는 방식으로 처리한다.
 * (예: 17850, 13047 등. users.csv 에 있는 user_id)
 */
export function LoginPage() {
  const [inputId, setInputId] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = () => {
    const userId = Number(inputId);
    if (!userId || Number.isNaN(userId)) {
      alert("숫자로 된 사용자 ID를 입력하세요. (예: 17850)");
      return;
    }
    login(userId);
    // 로그인 이벤트 기록
    trackEvent("login", { user_id: userId });
    navigate("/");
  };

  return (
    <div className="container">
      <div className="login-box">
        <h1 style={{ fontSize: "1.3rem" }}>로그인</h1>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.4rem" }}>
          데이터셋의 사용자 ID로 로그인합니다. (예: 17850)
        </p>
        <input
          type="number"
          placeholder="사용자 ID"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLogin()}
        />
        <button className="btn" onClick={handleLogin}>
          로그인
        </button>
      </div>
    </div>
  );
}
