import axios from "axios";

// 백엔드 API base URL. 환경변수(VITE_API_URL)가 있으면 그걸 쓰고 없으면 로컬 기본값.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});
