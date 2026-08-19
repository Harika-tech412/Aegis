import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import { api, setAuthToken } from "@/lib/api";

interface AuthState {
  token: string | null;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);

  const login = useCallback(async (user: string, password: string) => {
    const { access_token } = await api.login(user, password);
    setAuthToken(access_token);
    setToken(access_token);
    setUsername(user);
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setToken(null);
    setUsername(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
