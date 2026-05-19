import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import { getMe, logout as apiLogout } from '../lib/api';
import type { User } from '../lib/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function isUnauthorized(error: unknown) {
  return axios.isAxiosError(error) && error.response?.status === 401;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearAuthState = useCallback(() => {
    setUser(null);
  }, []);

  const loadCurrentUser = useCallback(async () => {
    const userData = await getMe();
    setUser(userData);
    return userData;
  }, []);

  const refreshUser = useCallback(async () => {
    setIsLoading(true);
    try {
      await loadCurrentUser();
    } catch (error) {
      if (!isUnauthorized(error)) {
        console.error('获取用户信息失败', error);
      }
      clearAuthState();
    } finally {
      setIsLoading(false);
    }
  }, [clearAuthState, loadCurrentUser]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const login = useCallback(async () => {
    setIsLoading(true);
    try {
      await loadCurrentUser();
    } catch (error) {
      console.error('登录获取用户信息失败', error);
      clearAuthState();
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [clearAuthState, loadCurrentUser]);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (error) {
      if (!isUnauthorized(error)) {
        console.error('退出登录失败', error);
      }
    } finally {
      clearAuthState();
      setIsLoading(false);
    }
  }, [clearAuthState]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>
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
