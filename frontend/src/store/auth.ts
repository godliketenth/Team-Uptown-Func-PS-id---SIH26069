import { create } from "zustand";
import { api, clearToken, getToken, setToken } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
  restore: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  login: async (email, password) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    const user = await api.me();
    set({ user });
    return user;
  },
  logout: () => {
    clearToken();
    set({ user: null });
  },
  restore: async () => {
    if (!getToken()) {
      set({ loading: false });
      return;
    }
    try {
      set({ user: await api.me(), loading: false });
    } catch {
      clearToken();
      set({ user: null, loading: false });
    }
  },
}));
