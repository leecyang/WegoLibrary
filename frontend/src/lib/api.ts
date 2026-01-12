import axios from 'axios';

const API_BASE = '/api';

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 添加请求拦截器，自动注入 Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// ============ 类型定义 ============

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  created_at: string;
}

export interface StatusData {
  is_configured: boolean;
  session_id_preview: string;
  major: number;
  minor: number;
  venue_major?: number;
  venue_minor?: number;
  last_checkin: string;
  last_checkin_result: string;
  auto_checkin_enabled?: boolean;
}

export interface AdminUserConfig {
  user_id: number;
  username: string;
  is_configured: boolean;
  last_checkin: string;
  status: string;
}

// ============ Auth API ============

export const login = async (username: string, password: string) => {
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);
  const res = await api.post<{ access_token: string; token_type: string }>('/auth/login', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

export const register = async (username: string, password: string) => {
  const res = await api.post<User>('/auth/register', { username, password });
  return res.data;
};

export const getMe = async () => {
  const res = await api.get<User>('/auth/me');
  return res.data;
};

// ============ Business API ============

export const getStatus = async () => {
  const res = await api.get<StatusData>('/status');
  return res.data;
};

export const updateConfig = async (session_id: string, venueMajor: number, venueMinor: number) => {
  const res = await api.post('/config', { session_id, venue_major: venueMajor, venue_minor: venueMinor });
  return res.data;
};

export const parseSessionIdFromUrl = async (url: string) => {
  const res = await api.post<{ session_id: string }>('/parse-sessionid', { url });
  return res.data;
};

export const triggerCheckIn = async () => {
  const res = await api.post('/checkin');
  return res.data;
};

export const triggerKeepAlive = async () => {
  const res = await api.post('/keepalive');
  return res.data;
};

export const enableAutoCheckIn = async () => {
  const res = await api.post('/auto-checkin/enable');
  return res.data;
};

export const disableAutoCheckIn = async () => {
  const res = await api.post('/auto-checkin/disable');
  return res.data;
};

// ============ Admin API ============

export const getAdminUsers = async () => {
  const res = await api.get<AdminUserConfig[]>('/admin/users');
  return res.data;
};

export const deleteAdminUser = async (userId: number) => {
  const res = await api.delete(`/admin/users/${userId}`);
  return res.data;
};

export const adminTriggerCheckIn = async (userId: number) => {
  const res = await api.post(`/admin/users/${userId}/checkin`);
  return res.data;
};
