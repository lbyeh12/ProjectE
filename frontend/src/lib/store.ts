import { create } from "zustand";
import { getCurrentUserId, setCurrentUserId, clearCurrentUserId } from "./tracker";

interface AuthState {
  userId: number | null;
  login: (userId: number) => void;
  logout: () => void;
}

// 새로고침해도 유지되도록 초기값을 sessionStorage에서 읽어온다.
export const useAuth = create<AuthState>((set) => ({
  userId: getCurrentUserId(),
  login: (userId) => {
    setCurrentUserId(userId);
    set({ userId });
  },
  logout: () => {
    clearCurrentUserId();
    set({ userId: null });
  },
}));
