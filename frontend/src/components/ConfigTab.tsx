import React, { useState, useEffect } from 'react';
import { Save, AlertCircle, CheckCircle2, QrCode, ClipboardPaste, Settings, MapPin } from 'lucide-react';
import type { AxiosError } from 'axios';
import { parseSessionIdFromUrl, updateConfig, type StatusData } from '../lib/api';
import { extractSessionIdFromText } from '../lib/sessionId';

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
    
    // 1. Try direct session ID
    const direct = extractSessionIdFromText(text);
    if (direct) {
      targetSessionId = direct;
    } else {
      // 2. Try parsing URL
      const res = await parseSessionIdFromUrl(text.trim());
      targetSessionId = res.session_id;
    }

    // 3. Save config
    const currentMajor = (currentData?.venue_major ?? currentData?.major) || 20;
    const currentMinor = (currentData?.venue_minor ?? currentData?.minor) || 9;
    const submitMajor = parseBeaconValue(major, currentMajor);
    const submitMinor = parseBeaconValue(minor, currentMinor);

    await updateConfig(targetSessionId, submitMajor, submitMinor);
    
    setMessage({ type: 'success', text: '登录成功！Session 已更新' });
    setLinkInput(''); 
    setShowLinkInput(false);
    onUpdate();
    setTimeout(() => setMessage(null), 3000);
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
      const axiosErr = err as AxiosError<{ detail?: string }>;
      let msg = rawMessage || '操作失败';
      if (axiosErr.response?.data?.detail) msg = axiosErr.response.data.detail;
      if (rawMessage === 'Read permission denied.') {
        msg = '无法读取剪贴板，请手动粘贴';
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
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.data?.detail) msg = axiosErr.response.data.detail;
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

  return (
    <div className="h-full flex flex-col px-4 pt-4 pb-32 animate-fade-in space-y-4 overflow-y-auto">
      
      {/* Connection Card */}
      <div className="glass-card overflow-hidden shrink-0">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-white/50">
          <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <QrCode className="w-5 h-5 text-primary" />
            连接微信
          </h2>
          {currentData?.is_configured && (
             <span className="status-badge-success">
               <CheckCircle2 className="w-3 h-3" /> 已连接
             </span>
          )}
        </div>
        
        <div className="p-6 space-y-6">
           {/* QR Code and Instructions */}
           <div className="flex flex-col items-center gap-4">
              <div className="w-40 h-40 bg-white p-2 rounded-xl shadow-sm border border-slate-100">
                <img src="/qr.png" alt="Scan to Login" className="w-full h-full object-contain" />
              </div>
              <div className="text-center space-y-1">
                <p className="text-sm font-medium text-slate-700">1. 使用微信“扫一扫”</p>
                <p className="text-xs text-slate-500">授权后复制跳转页面的链接</p>
              </div>
           </div>

           {/* Paste Button */}
           <div className="space-y-3">
             <button
                onClick={handlePasteAndLogin}
                disabled={loading}
                className="w-full btn-primary py-3 text-sm flex items-center justify-center gap-2 shadow-lg shadow-primary/20"
             >
                {loading ? <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></span> : <ClipboardPaste className="w-4 h-4" />}
                {loading ? '处理中...' : '2. 粘贴链接并登录'}
             </button>

             {/* Manual Input */}
             <div className={`transition-all duration-300 overflow-hidden ${showLinkInput ? 'max-h-24 opacity-100' : 'max-h-0 opacity-0'}`}>
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
        </div>
      </div>

      {/* Settings Card */}
      <div className="glass-card overflow-hidden shrink-0">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-white/50">
          <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Settings className="w-5 h-5 text-primary" />
            参数设置
          </h2>
        </div>
        
        <div className="p-5 space-y-5">
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
        </div>
      </div>
      
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
