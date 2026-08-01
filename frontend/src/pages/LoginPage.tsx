import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/store";

/**
 * 로그인 / 회원가입 페이지.
 *
 * 이 프로젝트는 UCI 데이터셋에 이미 존재하는 고객(CustomerID)으로
 * 로그인 체험을 하는 컨셉이라, "회원가입"은 새 계정을 만드는 게 아니라
 * 기존 user_id에 비밀번호를 설정하는 것이다.
 * (예: users.csv 에 있는 17850, 13047 같은 user_id 사용)
 */
export function LoginPage() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [inputId, setInputId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { login, signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async () => {
    const userId = Number(inputId);
    if (!userId || Number.isNaN(userId)) {
      setError("숫자로 된 사용자 ID를 입력하세요. (예: 17850)");
      return;
    }
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await signup(userId, password);
      } else {
        await login(userId, password);
      }
      navigate("/");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail ?? "요청 처리 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container">
      <div className="login-box">
        <h1 style={{ fontSize: "1.3rem" }}>{mode === "login" ? "로그인" : "회원가입"}</h1>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.4rem" }}>
          {mode === "login"
            ? "데이터셋의 사용자 ID와 비밀번호로 로그인합니다."
            : "데이터셋에 존재하는 사용자 ID에 비밀번호를 설정합니다. (예: 17850)"}
        </p>

        <input
          type="number"
          placeholder="사용자 ID"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
        />
        <input
          type="password"
          placeholder="비밀번호 (8자 이상)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />

        {error && (
          <p style={{ color: "var(--danger)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
            {error}
          </p>
        )}

        <button className="btn" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "처리 중..." : mode === "login" ? "로그인" : "회원가입"}
        </button>

        <button
          className="btn-ghost"
          style={{ width: "100%", marginTop: "0.6rem", padding: "0.5rem" }}
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "처음이신가요? 비밀번호 설정하기" : "이미 계정이 있나요? 로그인"}
        </button>
      </div>
    </div>
  );
}