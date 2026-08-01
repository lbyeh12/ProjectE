import axios from "axios";

// 백엔드 API base URL. 환경변수(VITE_API_URL)가 있으면 그걸 쓰고 없으면 로컬 기본값.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "projecte_access_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// 요청마다 로그인 토큰이 있으면 Authorization 헤더에 자동으로 실어 보낸다.
// 이 인터셉터 덕분에 각 API 호출 코드에서 매번 헤더를 신경 쓸 필요가 없다.
apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 토큰이 만료되었거나(401) 유효하지 않으면 저장된 토큰을 지운다.
// (화면 갱신은 각 페이지의 로직에 맡기고, 여기서는 만료된 토큰만 정리)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearToken();
    }
    return Promise.reject(error);
  }
);