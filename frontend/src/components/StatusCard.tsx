import React from 'react';
import { Activity, Clock, Server, CheckCircle2, XCircle } from 'lucide-react';
import type { StatusData } from '../lib/api';

interface Props {
  data: StatusData | null;
  loading: boolean;
}

export const StatusCard: React.FC<Props> = ({ data, loading }) => {
  if (loading || !data) {
    return (
      <div className="glass-card p-6 w-full animate-pulse h-48">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-slate-200 rounded w-full mb-2"></div>
        <div className="h-4 bg-slate-200 rounded w-2/3"></div>
      </div>
    );
  }

  const isAutoCheckinEnabled = !!data.auto_checkin_enabled;
  const formatTime = (value: string) => {
    if (value === 'Never') return '从未';
    // 简化时间显示，只显示时间部分（如果日期是今天）
    // 这里简单处理，截取后半部分
    return value.split(' ')[1] || value;
  };
  
  return (
    <div className="glass-card p-5 w-full relative overflow-hidden">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
          <Server className="w-5 h-5 text-primary" />
          系统状态
        </h2>
        <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${isAutoCheckinEnabled ? 'bg-green-50 text-green-700 border-green-200' : 'bg-slate-50 text-slate-500 border-slate-200'}`}>
          <div className={`w-1.5 h-1.5 rounded-full ${isAutoCheckinEnabled ? 'bg-green-500 animate-pulse' : 'bg-slate-400'}`}></div>
          {isAutoCheckinEnabled ? '补签中' : '未开启'}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 bg-slate-50/80 rounded-lg border border-slate-100">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-1">
            <Activity className="w-3.5 h-3.5" />
            补签
          </div>
          <div className="font-mono text-sm font-medium text-slate-700">{formatTime(data.last_checkin)}</div>
        </div>

        <div className="p-3 bg-slate-50/80 rounded-lg border border-slate-100">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-1">
            <Clock className="w-3.5 h-3.5" />
            状态
          </div>
          <div className="text-sm font-medium text-slate-700">{isAutoCheckinEnabled ? '开启' : '关闭'}</div>
        </div>
      </div>

      {data.last_checkin_result && (
        <div className={`mt-3 p-2.5 rounded-lg text-xs flex items-start gap-2 leading-relaxed ${data.last_checkin_result.includes('成功') ? 'bg-green-50 text-green-700 border border-green-100' : 'bg-red-50 text-red-700 border border-red-100'}`}>
          {data.last_checkin_result.includes('成功') ? (
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          )}
          <span className="break-all">{data.last_checkin_result.replace('签到成功:', '签到成功：').replace('扫码成功', '到馆验证成功')}</span>
        </div>
      )}
    </div>
  );
};
