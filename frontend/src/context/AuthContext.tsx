import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiGet, apiSend, clearTokens, setTokens } from '../lib/api';

type User = {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  tenant_name?: string;
  tenant_slug?: string;
  roles: string[];
  permissions: string[];
};

type AuthValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, shop?: string) => Promise<User | null>;
  logout: () => void;
  can: (permission: string) => boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (): Promise<User | null> => {
    if (!localStorage.getItem('billing_access')) {
      setLoading(false);
      return null;
    }
    try {
      const res = await apiGet<User>('/auth/me');
      setUser(res.data);
      return res.data;
    } catch {
      clearTokens();
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const login = useCallback(async (email: string, password: string, shop?: string) => {
    const res = await apiSend<{ access_token: string; refresh_token: string }>('post', '/auth/login', { email, password, shop });
    setTokens(res.data.access_token, res.data.refresh_token);
    return load();
  }, [load]);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const can = useCallback((permission: string) => {
    if (!user) return false;
    return user.permissions.includes(permission) || user.permissions.includes('all');
  }, [user]);

  const value = useMemo(() => ({ user, loading, login, logout, can }), [user, loading, login, logout, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
