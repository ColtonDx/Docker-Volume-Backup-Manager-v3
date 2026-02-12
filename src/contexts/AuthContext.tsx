import { createContext, useContext, useState, ReactNode } from "react";
import { login as apiLogin, logout as apiLogout, setToken } from "@/api";

interface AuthContextType {
  isAuthenticated: boolean;
  login: (password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return sessionStorage.getItem("dvbm_auth") === "true";
  });

  const login = async (password: string): Promise<boolean> => {
    try {
      await apiLogin(password);
      setIsAuthenticated(true);
      sessionStorage.setItem("dvbm_auth", "true");
      return true;
    } catch {
      return false;
    }
  };

  const logout = () => {
    apiLogout();
    setIsAuthenticated(false);
    sessionStorage.removeItem("dvbm_auth");
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
