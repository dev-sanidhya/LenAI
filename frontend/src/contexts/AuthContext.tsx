import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { exchangeApiKey, setAuthToken } from "../api/client";
import toast from "react-hot-toast";

interface AuthState {
  isAuthenticated: boolean;
  login: (apiKey: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const login = useCallback(async (apiKey: string) => {
    const res = await exchangeApiKey(apiKey);
    const { access_token } = res.data;
    // Token stored in JS memory only - no localStorage, no cookies.
    // Cleared on page refresh (user re-authenticates). This is intentional:
    // it limits the token lifetime window even if the page is left open.
    setAuthToken(access_token);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
