import React, { createContext, useContext, useState, useEffect } from 'react';
import { getMe } from '../lib/api';
import type { User } from '../lib/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = async () => {
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const userData = await getMe();
      setUser(userData);
    } catch (error) {
      console.error('获取用户信息失败', error);
      // 如果获取用户信息失败（token 无效），则登出
      logout();
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, [token]);

  const login = async (newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    
    // 立即获取用户信息，确保在跳转前 user 状态已更新
    try {
      // 这里的 getMe 会通过拦截器读取 localStorage 中最新的 token
      const userData = await getMe();
      setUser(userData);
    } catch (error) {
      console.error('登录获取用户信息失败', error);
      logout();
      throw error; // 抛出错误让 Login 组件捕获
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
