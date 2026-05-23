import React, { useState, useEffect, useRef, type ReactNode } from 'react';
import {
  Save,
  AlertCircle,
  CheckCircle2,
  QrCode,
  ClipboardPaste,
  Settings,
  MapPin,
  ChevronDown,
} from 'lucide-react';
import clsx from 'clsx';
import type { AxiosError } from 'axios';
import { parseSessionIdFromUrl, updateConfig, type StatusData, type WechatProfilePayload } from '../lib/api';
import { extractSessionIdFromText } from '../lib/sessionId';
import { WechatProfileCard } from './WechatProfileCard';
import { getWechatConnectionBadge } from '../lib/checkinMessage';

const WECHAT_QR_URL = 'https://imagebed.way2api.fun/file/wegolibrary/1779168428849_qr.png';

interface CollapsibleCardProps {
  title: string;
  icon: ReactNode;
  expanded: boolean;
  onToggle: () => void;
  trailing?: ReactNode;
  children: ReactNode;
  contentClassName?: string;
  locked?: boolean;
}

const CollapsibleCard: React.FC<CollapsibleCardProps> = ({
  title,
  icon,
  expanded,
  onToggle,
  trailing,
  children,
  contentClassName = 'p-6 space-y-6',
  locked = false,
}) => (
  <div className="glass-card overflow-hidden shrink-0">
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={clsx(
        'w-full p-4 flex items-center justify-between gap-3 bg-white/50 transition-colors text-left',
        locked ? 'cursor-default' : 'hover:bg-white/70 cursor-pointer',
      )}
    >
      <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2 min-w-0">
        {icon}
        <span className="truncate">{title}</span>
      </h2>
      <div className="flex items-center gap-2 shrink-0">
        {trailing}
        {!locked && (
          <ChevronDown
            className={clsx(
              'w-5 h-5 text-slate-400 transition-transform duration-300',
              expanded && 'rotate-180',
            )}
          />
        )}
      </div>
    </button>
    <div
      className={clsx(
        'grid transition-[grid-template-rows] duration-300 ease-in-out',
        expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
      )}
    >
      <div className="overflow-hidden">
        <div className={clsx('border-t border-slate-100', contentClassName)}>{children}</div>
      </div>
    </div>
  </div>
);

interface Props {
  currentData: StatusData | null;
  onUpdate: () => void;
}

export const ConfigTab: React.FC<Props> = ({ currentData, onUpdate }) => {
  const [major, setMajor] = useState('20');
  const [minor, setMinor] = useState('9');
  
  // Link input state
  const [linkInput, setLinkInput] = useState('');
  const [showLinkInput, setShowLinkInput] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [wechatExpanded, setWechatExpanded] = useState(false);
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  const previousWechatStatusRef = useRef<string | undefined>(undefined);

  const wechatStatus = currentData?.wechat_connection_status;
  const wechatMustStayOpen =
    !currentData?.is_configured || wechatStatus === 'disconnected' || wechatStatus === 'expired';
  const wechatLocked = wechatMustStayOpen;

  // 连接微信：未连接/过期强制展开；进入已连接时默认折叠，但允许手动展开。
  useEffect(() => {
    if (wechatMustStayOpen) {
      setWechatExpanded(true);
    } else if (
      wechatStatus === 'connected'
      && previousWechatStatusRef.current !== 'connected'
    ) {
      setWechatExpanded(false);
    }
    previousWechatStatusRef.current = wechatStatus;
  }, [wechatMustStayOpen, wechatStatus]);

  const parseBeaconValue = (raw: string, fallback: number) => {
    const trimmed = (raw ?? '').trim();
    if (!trimmed) return fallback;
    const n = Number.parseInt(trimmed, 10);
    if (!Number.isFinite(n) || Number.isNaN(n)) {
      throw new Error('参数必须为数字');
    }
    if (n < 1 || n > 65535) {
      throw new Error('参数范围为 1-65535');
    }
    return n;
  };

  useEffect(() => {
    if (currentData) {
      const currentMajor = currentData.venue_major ?? currentData.major;
      const currentMinor = currentData.venue_minor ?? currentData.minor;
      setMajor(currentMajor && currentMajor > 0 ? currentMajor.toString() : '20');
      setMinor(currentMinor && currentMinor > 0 ? currentMinor.toString() : '9');
    }
  }, [currentData]);

  const processText = async (text: string) => {
    if (!text || !text.trim()) {
      throw new Error('内容为空');
    }

    let targetSessionId = '';
    let profilePayload: WechatProfilePayload | null | undefined = undefined;
    let connectWarning: string | null | undefined;

    // 1. Try direct session ID
    const direct = extractSessionIdFromText(text);
    if (direct) {
      targetSessionId = direct;
    } else {
      // 2. 一次粘贴双换票（auth → wechatAuth）
      const res = await parseSessionIdFromUrl(text.trim());
      targetSessionId = res.session_id;
      connectWarning = res.warning;
      if (res.profile && Object.keys(res.profile).length > 0) {
        profilePayload = res.profile;
      }
    }

    // 3. Save config
    const currentMajor = (currentData?.venue_major ?? currentData?.major) || 20;
    const currentMinor = (currentData?.venue_minor ?? currentData?.minor) || 9;
    const submitMajor = parseBeaconValue(major, currentMajor);
    const submitMinor = parseBeaconValue(minor, currentMinor);

    await updateConfig(targetSessionId, submitMajor, submitMinor, profilePayload);

    setMessage({
      type: 'success',
      text: connectWarning
        ? `凭据已保存。${connectWarning}`
        : '登录成功！微信凭据已更新',
    });
    setLinkInput('');
    setShowLinkInput(false);
    onUpdate();
    setTimeout(() => setMessage(null), 5000);
  };

  const handlePasteAndLogin = async () => {
    setLoading(true);
    setMessage(null);
    try {
      // 优先尝试读取剪贴板
      let text = '';
      try {
        text = await navigator.clipboard.readText();
      } catch {
        // 读取失败，不报错，而是显示手动输入框
        setShowLinkInput(true);
        throw new Error('无法读取剪贴板，请在下方手动粘贴链接');
      }

      await processText(text);

    } catch (err: unknown) {
      const rawMessage = err instanceof Error ? err.message : '';
      const axiosErr = err as AxiosError<{ detail?: string | { msg?: string }[] }>;
      let msg = rawMessage || '操作失败';
      const detail = axiosErr.response?.data?.detail;
      if (typeof detail === 'string') msg = detail;
      else if (Array.isArray(detail)) msg = detail.map((d) => d?.msg || String(d)).join('; ');
      if (rawMessage === 'Read permission denied.') {
        msg = '无法读取剪贴板，请手动粘贴';
        setShowLinkInput(true);
      }
      if (msg.includes('微信连接失败')) {
        setShowLinkInput(true);
      }
      setMessage({ type: 'error', text: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleManualInputSubmit = async () => {
    if (!linkInput.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      await processText(linkInput);
    } catch (err: unknown) {
      let msg = '解析失败，请确认链接正确';
      const axiosErr = err as AxiosError<{ detail?: string | { msg?: string }[] }>;
      const detail = axiosErr.response?.data?.detail;
      if (typeof detail === 'string') msg = detail;
      else if (Array.isArray(detail)) msg = detail.map((d) => d?.msg || String(d)).join('; ');
      if (msg.includes('微信连接失败')) {
        setShowLinkInput(true);
      }
      setMessage({ type: 'error', text: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const submitMajor = parseBeaconValue(major, 20);
      const submitMinor = parseBeaconValue(minor, 9);
      await updateConfig('', submitMajor, submitMinor);
      setMessage({ type: 'success', text: '配置已保存' });
      onUpdate();
      setTimeout(() => setMessage(null), 3000);
    } catch (err: unknown) {
      const rawMessage = err instanceof Error ? err.message : '';
      setMessage({ type: 'error', text: rawMessage || '保存失败' });
    } finally {
      setLoading(false);
    }
  };

  const wechatBadge = getWechatConnectionBadge(currentData?.wechat_connection_status);

  return (
    <div className="h-full flex flex-col px-4 pt-4 pb-bottom-nav animate-fade-in space-y-4 overflow-y-auto scrollbar-none">

      <WechatProfileCard
        profileDisplay={currentData?.profile_display ?? (currentData?.is_configured ? 'pending' : 'none')}
        profile={currentData?.wechat_profile}
      />

      <CollapsibleCard
        title="连接微信"
        icon={<QrCode className="w-5 h-5 text-primary shrink-0" />}
        expanded={wechatExpanded}
        onToggle={() => {
          if (!wechatLocked) {
            setWechatExpanded((v) => !v);
          }
        }}
        locked={wechatLocked}
        trailing={
          wechatBadge ? (
            <span className={wechatBadge.className}>
              {wechatBadge.label === '已连接' ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : null}
              {wechatBadge.label}
            </span>
          ) : null
        }
      >
        <div className="flex flex-col items-center gap-4">
          <div className="w-40 h-40 bg-white p-2 rounded-xl shadow-sm border border-slate-100">
            <img src={WECHAT_QR_URL} alt="Scan to Login" className="w-full h-full object-contain" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-sm font-medium text-slate-700">1. 使用微信“扫一扫”</p>
            <p className="text-xs text-slate-500">授权后复制跳转页面的链接</p>
          </div>
        </div>

        <div className="space-y-3">
          <button
            onClick={handlePasteAndLogin}
            disabled={loading}
            className="w-full btn-primary py-3 text-sm flex items-center justify-center gap-2 shadow-lg shadow-primary/20"
          >
            {loading ? (
              <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <ClipboardPaste className="w-4 h-4" />
            )}
            {loading ? '处理中...' : '2. 粘贴链接并登录'}
          </button>

          <div
            className={clsx(
              'transition-all duration-300 overflow-hidden',
              showLinkInput ? 'max-h-24 opacity-100' : 'max-h-0 opacity-0',
            )}
          >
            <div className="flex gap-2">
              <input
                value={linkInput}
                onChange={(e) => setLinkInput(e.target.value)}
                placeholder="在此手动粘贴微信链接..."
                className="input-field text-xs font-mono flex-1"
              />
              <button
                onClick={handleManualInputSubmit}
                disabled={loading || !linkInput}
                className="btn-secondary px-3 py-2 text-xs whitespace-nowrap"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      </CollapsibleCard>

      <CollapsibleCard
        title="参数设置"
        icon={<Settings className="w-5 h-5 text-primary shrink-0" />}
        expanded={settingsExpanded}
        onToggle={() => setSettingsExpanded((v) => !v)}
        trailing={
          !settingsExpanded ? (
            <span className="text-xs text-slate-500 font-mono">
              {major}/{minor}
            </span>
          ) : null
        }
        contentClassName="p-5 space-y-5"
      >
        <div className="info-card-blue flex items-start gap-3">
          <MapPin className="w-5 h-5 text-primary shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-primary mb-1">场馆定位参数</div>
            <div className="text-xs text-slate-600 leading-relaxed">
              Major 和 Minor 是场馆的蓝牙信标编号（范围 1-65535）。
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 mb-2">
              Major
            </label>
            <input
              type="number"
              value={major}
              onChange={(e) => setMajor(e.target.value)}
              className="input-field text-center text-lg font-mono font-semibold"
              placeholder="20"
              min={1}
              max={65535}
            />
          </div>
          <div>
            <label className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 mb-2">
              Minor
            </label>
            <input
              type="number"
              value={minor}
              onChange={(e) => setMinor(e.target.value)}
              className="input-field text-center text-lg font-mono font-semibold"
              placeholder="9"
              min={1}
              max={65535}
            />
          </div>
        </div>

        <button
          onClick={handleSaveConfig}
          disabled={loading}
          className="w-full btn-secondary py-3 text-sm flex items-center justify-center gap-2"
        >
          <Save className="w-4 h-4" />
          保存参数
        </button>
      </CollapsibleCard>
      
      {message && (
        <div className={`fixed top-4 left-4 right-4 z-50 p-4 rounded-xl shadow-lg border flex items-center gap-3 animate-in fade-in slide-in-from-top-4 ${
          message.type === 'success' 
            ? 'bg-white border-green-100 text-green-700' 
            : 'bg-white border-red-100 text-red-700'
        }`}>
          {message.type === 'success' ? <CheckCircle2 className="w-5 h-5 text-green-500" /> : <AlertCircle className="w-5 h-5 text-red-500" />}
          <span className="font-medium">{message.text}</span>
        </div>
      )}

    </div>
  );
};
