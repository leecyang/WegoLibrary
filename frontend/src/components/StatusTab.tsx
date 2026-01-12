import React from 'react';
import { Activity, Clock, Server, CheckCircle2, XCircle, Wifi, WifiOff, Bluetooth, BluetoothOff } from 'lucide-react';
import type { StatusData } from '../lib/api';

interface Props {
  data: StatusData | null;
  loading: boolean;
}

export const StatusTab: React.FC<Props> = ({ data, loading }) => {
  if (loading || !data) {
    return (
      <div className="h-full flex flex-col p-4 gap-4 animate-fade-in">
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="h-6 bg-slate-100 rounded-lg w-24 animate-pulse" />
            <div className="h-7 bg-slate-100 rounded-full w-16 animate-pulse" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="h-24 bg-slate-50 rounded-xl animate-pulse" />
            <div className="h-24 bg-slate-50 rounded-xl animate-pulse" />
          </div>
        </div>
        <div className="glass-card p-4 h-16 animate-pulse" />
        <div className="glass-card p-4 h-16 animate-pulse" />
      </div>
    );
  }

  const isNever = (value: string) => value === 'Never' || value === '从未';
  const isConfigured = data.is_configured;
  const major = data.venue_major ?? data.major;
  const minor = data.venue_minor ?? data.minor;
  const isBluetoothConfigured = major !== 0 && minor !== 0;
  const isSuccess = data.last_checkin_result?.includes('成功');
  const isAutoCheckinEnabled = !!data.auto_checkin_enabled;
  const checkinResultText = (data.last_checkin_result || '')
    .replace('签到成功:', '签到成功：')
    .replace('扫码成功', '到馆验证成功');

  const formatTime = (value: string) => {
    if (isNever(value)) return '--:--';
    return value.split(' ')[1] || value;
  };

  const formatDate = (value: string) => {
    if (isNever(value)) return '暂无记录';
    const datePart = value.split(' ')[0] || '';
    // 简化日期显示：只显示月-日
    const parts = datePart.split('-');
    if (parts.length === 3) {
      return `${parts[1]}月${parts[2]}日`;
    }
    return datePart;
  };

  return (
    <div className="h-full flex flex-col px-4 pt-4 pb-24 animate-fade-in gap-4 overflow-y-auto">
      {/* 主状态卡片 */}
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Server className="w-5 h-5 text-primary" />
            运行状态
          </h2>
          <div className={`status-badge ${isAutoCheckinEnabled ? 'status-badge-success' : 'status-badge-neutral'}`}>
            <div className={`w-1.5 h-1.5 rounded-full ${isAutoCheckinEnabled ? 'bg-success animate-pulse' : 'bg-slate-400'}`} />
            {isAutoCheckinEnabled ? '补签中' : '未开启'}
          </div>
        </div>

        {/* 状态网格 */}
        <div className="grid grid-cols-2 gap-3">
          <div className="info-card-blue">
            <div className={`flex items-center gap-2 mb-2 ${isAutoCheckinEnabled ? 'text-primary' : 'text-[#6c757d]'}`}>
              <Activity className="w-4 h-4" />
              <span className="text-xs font-semibold">上次补签时间</span>
            </div>
            <div className={`font-mono text-2xl font-bold tracking-tight ${isAutoCheckinEnabled ? 'text-slate-800' : 'text-[#6c757d]'}`}>
              {formatTime(data.last_checkin)}
            </div>
            <div className={`text-xs mt-1.5 ${isAutoCheckinEnabled ? 'text-slate-500' : 'text-[#6c757d]'}`}>{formatDate(data.last_checkin)}</div>
          </div>

          <div className="info-card-orange">
            <div className="flex items-center gap-2 text-cta mb-2">
              <Clock className="w-4 h-4" />
              <span className="text-xs font-semibold">补签状态</span>
            </div>
            <div className="text-2xl font-bold text-slate-800 tracking-tight">
              {isAutoCheckinEnabled ? '开启' : '关闭'}
            </div>
            <div className="text-xs text-slate-500 mt-1.5">
              {isAutoCheckinEnabled ? '每18分钟执行，至24:00停止' : '点击「开启补签」开始补签'}
            </div>
          </div>
        </div>
      </div>

      {/* 签到结果卡片 */}
      {data.last_checkin_result && (
        <div className={`glass-card p-4 flex items-start gap-3 animate-slide-up ${
          isSuccess ? 'info-card-success' : 'info-card-danger'
        }`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
            isSuccess ? 'bg-success/10' : 'bg-danger/10'
          }`}>
            {isSuccess ? (
              <CheckCircle2 className="w-5 h-5 text-success" />
            ) : (
              <XCircle className="w-5 h-5 text-danger" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className={`text-sm font-semibold mb-0.5 ${
              isSuccess ? 'text-success' : 'text-danger'
            }`}>
              {isSuccess ? '签到成功' : '签到失败'}
            </div>
            <div className={`text-sm break-all leading-relaxed ${
              isSuccess ? 'text-green-700' : 'text-red-700'
            }`}>
              {checkinResultText}
            </div>
          </div>
        </div>
      )}

      {/* 连接状态指示 */}
      <div className="glass-card-interactive p-4 flex items-center gap-4">
        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
          isConfigured ? 'bg-success-light' : 'bg-slate-100'
        }`}>
          {isConfigured ? (
            <Wifi className="w-6 h-6 text-success" />
          ) : (
            <WifiOff className="w-6 h-6 text-slate-400" />
          )}
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-800">
            {isConfigured ? '微信已连接' : '微信未连接'}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {isConfigured ? '补签开启后将自动执行蓝牙补签' : '请前往「配置」页面扫码绑定'}
          </div>
        </div>
        <div className={`w-2.5 h-2.5 rounded-full ${isConfigured ? 'bg-success' : 'bg-slate-300'}`} />
      </div>

      {/* 蓝牙配置状态指示 */}
      <div className="glass-card-interactive p-4 flex items-center gap-4">
        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
          isBluetoothConfigured ? 'bg-blue-50' : 'bg-slate-100'
        }`}>
          {isBluetoothConfigured ? (
            <Bluetooth className="w-6 h-6 text-blue-500" />
          ) : (
            <BluetoothOff className="w-6 h-6 text-slate-400" />
          )}
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-800">
            {isBluetoothConfigured ? '蓝牙参数已配置' : '蓝牙参数未配置'}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {isBluetoothConfigured ? `Major: ${major}, Minor: ${minor}` : '请前往「配置」页面设置参数'}
          </div>
        </div>
        <div className={`w-2.5 h-2.5 rounded-full ${isBluetoothConfigured ? 'bg-blue-500' : 'bg-slate-300'}`} />
      </div>
    </div>
  );
};
