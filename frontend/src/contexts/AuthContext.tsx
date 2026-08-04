import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setAccessToken } from "../lib/api";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (data: unknown) => Promise<User>;
  updateProfile: (data: unknown) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .refresh()
      .then(({ access }) => {
        setAccessToken(access);
        return api.me();
      })
      .then((profile) => {
        if (active) setUser(profile);
      })
      .catch(() => setAccessToken(null))
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login({ email, password });
    setAccessToken(result.access);
    setUser(result.user);
    return result.user;
  }, []);

  const register = useCallback(async (data: unknown) => {
    const result = await api.register(data);
    setAccessToken(result.access);
    setUser(result.user);
    return result.user;
  }, []);

  const updateProfile = useCallback(async (data: unknown) => {
    const result = await api.updateMe(data);
    setUser(result);
    return result;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, ready, login, register, updateProfile, logout }),
    [user, ready, login, register, updateProfile, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
