import { apiClient } from "./client";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  user_id: number;
  country: string | null;
}

export async function signup(userId: number, password: string): Promise<UserResponse> {
  const res = await apiClient.post<UserResponse>("/auth/signup", {
    user_id: userId,
    password,
  });
  return res.data;
}

export async function login(userId: number, password: string): Promise<TokenResponse> {
  const res = await apiClient.post<TokenResponse>("/auth/login", {
    user_id: userId,
    password,
  });
  return res.data;
}

export async function fetchMe(): Promise<UserResponse> {
  const res = await apiClient.get<UserResponse>("/auth/me");
  return res.data;
}
