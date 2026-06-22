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
  BookOpen,
} from 'lucide-react';
import clsx from 'clsx';
import type { AxiosError } from 'axios';
import {
  getLocationPresets,
  parseSessionIdFromUrl,
  updateConfig,
  type LocationPreset,
  type StatusData,
  type WechatProfilePayload,
} from '../lib/api';
import { extractSessionIdFromText } from '../lib/sessionId';
import { WechatProfileCard } from './WechatProfileCard';
import { getWechatConnectionBadge } from '../lib/checkinMessage';
import { AnnouncementMarkdown } from './AnnouncementMarkdown';
import { USE_GUIDE_CONTENT } from '../content/useGuide';

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
  const [requiresSecondLink, setRequiresSecondLink] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [wechatExpanded, setWechatExpanded] = useState(false);
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  const [guideExpanded, setGuideExpanded] = useState(false);
  const [locationPresetsExpanded, setLocationPresetsExpanded] = useState(false);
  const [locationPresets, setLocationPresets] = useState<LocationPreset[]>([]);
  const [locationPresetsLoaded, setLocationPresetsLoaded] = useState(false);
  const [locationPresetsError, setLocationPresetsError] = useState(false);
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

  useEffect(() => {
    let cancelled = false;

    const loadLocationPresets = async () => {
      try {
        const presets = await getLocationPresets();
        if (!cancelled) {
          setLocationPresets(presets);
          setLocationPresetsError(false);
        }
      } catch (error) {
        console.error('获取定位复用信息失败', error);
        if (!cancelled) {
          setLocationPresetsError(true);
        }
      } finally {
        if (!cancelled) {
          setLocationPresetsLoaded(true);
        }
      }
    };

    loadLocationPresets();

    return () => {
      cancelled = true;
    };
  }, []);

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
      setRequiresSecondLink(false);
    } else {
      // 2. 一次粘贴双换票（auth → wechatAuth）
      const res = await parseSessionIdFromUrl(text.trim());
      if (res.requires_second_link) {
        setRequiresSecondLink(true);
        setLinkInput('');
        setShowLinkInput(false);
        setMessage({
          type: 'success',
          text: '第一步已完成。请回到微信重新授权，再粘贴第二条新链接完成连接。不要使用微信内置网页打开链接，请改用其他浏览器。',
        });
        return;
      }
      if (!res.session_id) {
        throw new Error('未获取到签到凭据，请重新授权');
      }
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
    setRequiresSecondLink(false);
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
      if (msg.includes('两步连接')) {
        setRequiresSecondLink(false);
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
      if (msg.includes('两步连接')) {
        setRequiresSecondLink(false);
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

  const handleApplyLocationPreset = (preset: LocationPreset) => {
    setMajor(preset.venue_major.toString());
    setMinor(preset.venue_minor.toString());
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
          {requiresSecondLink && (
            <div className="rounded-lg border border-primary/20 bg-primary-light px-3 py-3 text-left">
              <p className="text-sm font-semibold text-primary">第一步已完成</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                请回到微信重新授权一次，再粘贴新生成的第二条链接完成连接。不要使用微信内置网页打开链接，请改用其他浏览器。
              </p>
            </div>
          )}

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
            {loading
              ? '处理中...'
              : requiresSecondLink
                ? '粘贴第二条新链接'
                : '2. 粘贴链接并登录'}
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
              可手动填写参数，或复用站内已知图书馆定位信息。
            </div>
          </div>
        </div>

        {locationPresets.length > 0 ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 overflow-hidden">
            <button
              type="button"
              onClick={() => setLocationPresetsExpanded((v) => !v)}
              aria-expanded={locationPresetsExpanded}
              className="w-full px-3 py-3 flex items-center justify-between gap-3 text-left hover:bg-white/60 transition-colors"
            >
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-800">已知图书馆定位信息</div>
                <div className="mt-0.5 text-xs text-slate-400">{locationPresets.length} 个地点可复用</div>
              </div>
              <ChevronDown
                className={clsx(
                  'w-4 h-4 text-slate-400 shrink-0 transition-transform duration-300',
                  locationPresetsExpanded && 'rotate-180',
                )}
              />
            </button>
            <div
              className={clsx(
                'grid transition-[grid-template-rows] duration-300 ease-in-out',
                locationPresetsExpanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
              )}
            >
              <div className="overflow-hidden">
                <div className="border-t border-slate-200 p-3 space-y-2">
                  {locationPresets.map((preset) => (
                    <div
                      key={`${preset.school}-${preset.area_name}`}
                      className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 bg-white px-3 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium leading-6 text-slate-800 break-words">
                          {preset.label}
                        </div>
                        <div className="mt-1 font-mono text-xs text-slate-500">
                          Major: {preset.venue_major} / Minor: {preset.venue_minor}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleApplyLocationPreset(preset)}
                        className="btn-secondary px-3 py-2 text-xs shrink-0"
                      >
                        使用
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            {locationPresetsLoaded
              ? locationPresetsError
                ? '暂时无法加载站内已知图书馆定位信息，可继续手动填写。'
                : '暂无站内已知图书馆定位信息，可先手动填写。'
              : '正在加载站内已知图书馆定位信息...'}
          </div>
        )}

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

      <CollapsibleCard
        title="使用说明"
        icon={<BookOpen className="w-5 h-5 text-primary shrink-0" />}
        expanded={guideExpanded}
        onToggle={() => setGuideExpanded((v) => !v)}
        contentClassName="p-5"
      >
        <AnnouncementMarkdown content={USE_GUIDE_CONTENT} />
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
