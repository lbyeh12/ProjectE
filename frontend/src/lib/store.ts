import { create } from "zustand";
import { getToken, setToken, clearToken } from "../api/client";
import { login as loginApi, signup as signupApi, fetchMe } from "../api/auth";

interface AuthState {
  userId: number | null;
  isLoading: boolean;
  login: (userId: number, password: string) => Promise<void>;
  signup: (userId: number, password: string) => Promise<void>;
  logout: () => void;
  /** 새로고침 시 저장된 토큰이 아직 유효한지 서버에 확인한다. */
  restoreSession: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  userId: null,
  isLoading: true,

  login: async (userId, password) => {
    const { access_token } = await loginApi(userId, password);
    setToken(access_token);
    set({ userId });
  },

  signup: async (userId, password) => {
    await signupApi(userId, password);
    // 회원가입 성공 후 바로 로그인까지 진행한다.
    const { access_token } = await loginApi(userId, password);
    setToken(access_token);
    set({ userId });
  },

  logout: () => {
    clearToken();
    set({ userId: null });
  },

  restoreSession: async () => {
    const token = getToken();
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const me = await fetchMe();
      set({ userId: me.user_id, isLoading: false });
    } catch {
      // 토큰이 만료/무효하면 로그아웃 상태로 정리한다.
      clearToken();
      set({ userId: null, isLoading: false });
    }
  },
}));