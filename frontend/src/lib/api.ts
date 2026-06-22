import axios from 'axios';

const API_BASE = '/api';

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ============ 类型定义 ============

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  created_at: string;
}

export type ProfileDisplay = 'none' | 'pending' | 'ready';

export type WechatConnectionStatus =
  | 'disconnected'
  | 'connected'
  | 'expired'
  | 'unauthorized';

export interface WechatProfile {
  nick?: string | null;
  avatar?: string | null;
  student_name?: string | null;
  student_no?: string | null;
  sch?: string | null;
  area_name?: string | null;
  traceint_user_id?: number | null;
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
  profile_display?: ProfileDisplay;
  wechat_profile?: WechatProfile | null;
  wechat_connection_status?: WechatConnectionStatus;
}

export interface AnnouncementData {
  has_announcement: boolean;
  content: string;
  published_at: string | null;
}

export interface LocationPreset {
  school: string;
  area_name?: string | null;
  label: string;
  venue_major: number;
  venue_minor: number;
}

export interface AdminAnnouncementData {
  draft_content: string;
  published_content: string;
  is_published: boolean;
  updated_at: string | null;
  published_at: string | null;
}

export interface UpdateAnnouncementDraftRequest {
  content: string;
}

export interface AdminUserConfig {
  user_id: number;
  username: string;
  is_configured: boolean;
  last_checkin: string;
  status: string;
  profile_display?: ProfileDisplay;
  wechat_nick?: string | null;
  wechat_student_name?: string | null;
  wechat_student_no?: string | null;
  wechat_sch?: string | null;
  wechat_avatar?: string | null;
}

export interface WechatProfilePayload {
  traceint_user_id?: number | null;
  nick?: string | null;
  avatar?: string | null;
  student_name?: string | null;
  student_no?: string | null;
  sch?: string | null;
  area_name?: string | null;
  fetched_at?: string | null;
}

export interface ParseSessionIdResponse {
  session_id: string | null;
  profile: WechatProfilePayload | null;
  warning?: string | null;
  requires_second_link?: boolean;
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

export const logout = async () => {
  const res = await api.post<{ message: string }>('/auth/logout');
  return res.data;
};

// ============ Business API ============

export const getStatus = async () => {
  const res = await api.get<StatusData>('/status');
  return res.data;
};

export const getAnnouncement = async () => {
  const res = await api.get<AnnouncementData>('/announcement');
  return res.data;
};

export const getLocationPresets = async () => {
  const res = await api.get<LocationPreset[]>('/location-presets');
  return res.data;
};

export const updateConfig = async (
  session_id: string,
  venueMajor: number,
  venueMinor: number,
  profile?: WechatProfilePayload | null,
) => {
  const body: Record<string, unknown> = {
    session_id,
    venue_major: venueMajor,
    venue_minor: venueMinor,
  };
  if (profile) {
    body.profile = profile;
  }
  const res = await api.post('/config', body);
  return res.data;
};

export const parseSessionIdFromUrl = async (url: string) => {
  const res = await api.post<ParseSessionIdResponse>('/parse-sessionid', { url });
  return res.data;
};

export interface CheckInResult {
  success: boolean;
  message: string;
}

export const triggerCheckIn = async () => {
  const res = await api.post<CheckInResult>('/checkin');
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

export const getAdminAnnouncement = async () => {
  const res = await api.get<AdminAnnouncementData>('/admin/announcement');
  return res.data;
};

export const updateAdminAnnouncementDraft = async (payload: UpdateAnnouncementDraftRequest) => {
  const res = await api.put<AdminAnnouncementData>('/admin/announcement/draft', payload);
  return res.data;
};

export const publishAdminAnnouncement = async () => {
  const res = await api.post<AdminAnnouncementData>('/admin/announcement/publish');
  return res.data;
};

export const unpublishAdminAnnouncement = async () => {
  const res = await api.post<AdminAnnouncementData>('/admin/announcement/unpublish');
  return res.data;
};

export const deleteAdminUser = async (userId: number) => {
  const res = await api.delete(`/admin/users/${userId}`);
  return res.data;
};

export const adminLogoutUser = async (userId: number) => {
  const res = await api.post(`/admin/users/${userId}/logout`);
  return res.data;
};
