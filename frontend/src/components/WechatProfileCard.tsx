import React, { useState } from 'react';
import { User, UserCircle, AlertCircle } from 'lucide-react';
import type { ProfileDisplay, WechatProfile } from '../lib/api';

interface Props {
  profileDisplay?: ProfileDisplay;
  profile?: WechatProfile | null;
}

export const WechatProfileCard: React.FC<Props> = ({
  profileDisplay = 'none',
  profile,
}) => {
  const [avatarError, setAvatarError] = useState(false);

  if (profileDisplay === 'none') {
    return (
      <div className="glass-card p-4 shrink-0">
        <div className="info-card-blue flex items-start gap-3 py-3">
          <UserCircle className="w-5 h-5 text-slate-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-slate-600">尚未连接微信</div>
            <div className="text-xs text-slate-500 mt-0.5">连接后可在此查看微信个人资料</div>
          </div>
        </div>
      </div>
    );
  }

  if (profileDisplay === 'pending') {
    return (
      <div className="glass-card p-4 shrink-0">
        <div className="info-card-orange flex items-start gap-3 py-3">
          <AlertCircle className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-orange-800">已连接微信，暂无个人信息</div>
            <div className="text-xs text-orange-700/80 mt-0.5 leading-relaxed">
              请重新粘贴最新授权链接以同步昵称、头像与校区信息
            </div>
          </div>
        </div>
      </div>
    );
  }

  const nick = profile?.nick || '微信用户';
  const showAvatar = profile?.avatar && !avatarError;

  return (
    <div className="glass-card p-4 shrink-0">
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-slate-100 border border-slate-200 overflow-hidden shrink-0 flex items-center justify-center">
          {showAvatar ? (
            <img
              src={profile!.avatar!}
              alt={nick}
              className="w-full h-full object-cover"
              onError={() => setAvatarError(true)}
            />
          ) : (
            <User className="w-7 h-7 text-slate-400" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-base font-semibold text-slate-800 truncate">{nick}</div>
          {profile?.sch && (
            <div className="text-xs text-slate-500 mt-0.5 truncate">{profile.sch}</div>
          )}
          {(profile?.student_name || profile?.student_no) && (
            <div className="text-xs text-slate-500 mt-0.5 truncate">
              {[profile.student_name, profile.student_no].filter(Boolean).join(' · ')}
            </div>
          )}
          {profile?.area_name && (
            <div className="text-xs text-slate-400 mt-0.5 truncate">{profile.area_name}</div>
          )}
        </div>
      </div>
    </div>
  );
};
