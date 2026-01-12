import React, { useState } from 'react';
import { MapPin, RefreshCw, X, Zap } from 'lucide-react';
import { triggerCheckIn, enableAutoCheckIn, disableAutoCheckIn } from '../lib/api';

interface Props {
  onUpdate: () => void;
  autoCheckinEnabled?: boolean;
}

export const FloatingActions: React.FC<Props> = ({ onUpdate, autoCheckinEnabled = false }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [loadingCheckIn, setLoadingCheckIn] = useState(false);
  const [loadingAutoCheckin, setLoadingAutoCheckin] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'danger'; text: string } | null>(null);

  const showFeedback = (type: 'success' | 'danger', text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 2000);
  };

  const handleCheckIn = async () => {
    setLoadingCheckIn(true);
    try {
      await triggerCheckIn();
      onUpdate();
      showFeedback('success', '签到成功');
    } catch {
      showFeedback('danger', '签到失败');
    } finally {
      setLoadingCheckIn(false);
      setIsOpen(false);
    }
  };

  const handleToggleAutoCheckin = async () => {
    setLoadingAutoCheckin(true);
    try {
      if (autoCheckinEnabled) {
        await disableAutoCheckIn();
        showFeedback('danger', '关闭成功');
      } else {
        await enableAutoCheckIn();
        showFeedback('success', '开启成功');
      }
      onUpdate();
    } catch {
      showFeedback('danger', autoCheckinEnabled ? '关闭失败' : '开启失败');
    } finally {
      setLoadingAutoCheckin(false);
      setIsOpen(false);
    }
  };

  return (
    <>
      {/* 反馈提示 Toast */}
      {feedback && (
        <div className="fixed top-20 left-0 right-0 flex justify-center z-50 pointer-events-none">
          <div className={`px-4 py-2.5 rounded-full shadow-lg animate-slide-up pointer-events-auto ${
            feedback.type === 'success'
              ? 'bg-success text-white'
              : 'bg-danger text-white'
          }`}>
            <span className="text-sm font-medium">{feedback.text}</span>
          </div>
        </div>
      )}

      {/* 遮罩层 */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 animate-fade-in"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* 悬浮按钮组 */}
      <div className="fixed right-4 bottom-24 z-50 flex flex-col items-end gap-3 pointer-events-none">
        {/* 展开的操作按钮 */}
        <div className={`flex flex-col gap-3 transition-all duration-300 ease-out ${
          isOpen
            ? 'opacity-100 translate-y-0 scale-100 pointer-events-auto'
            : 'opacity-0 translate-y-2 scale-95 pointer-events-none'
        }`}>
          {/* 补签开关 */}
          <button
            onClick={handleToggleAutoCheckin}
            disabled={loadingAutoCheckin}
            className={`flex items-center gap-2.5 pl-4 pr-3 py-3 text-white rounded-2xl shadow-lg active:scale-95 transition-all touch-manipulation touch-target select-none ${
              autoCheckinEnabled
                ? 'bg-[#dc3545] shadow-[#dc3545]/30'
                : 'bg-primary shadow-primary/30'
            }`}
            aria-label={autoCheckinEnabled ? '关闭补签' : '开启补签'}
          >
            <span className="text-sm font-semibold">{autoCheckinEnabled ? '关闭补签' : '开启补签'}</span>
            <div className={`w-8 h-8 bg-white/20 rounded-xl flex items-center justify-center ${
              loadingAutoCheckin ? 'animate-spin' : ''
            }`}>
              <RefreshCw className="w-4 h-4" />
            </div>
          </button>

          {/* 签到按钮 */}
          <button
            onClick={handleCheckIn}
            disabled={loadingCheckIn}
            className="flex items-center gap-2.5 pl-4 pr-3 py-3 bg-cta text-white rounded-2xl shadow-lg shadow-cta/30 active:scale-95 transition-all touch-manipulation touch-target select-none"
            aria-label="立即签到"
          >
            <span className="text-sm font-semibold">立即签到</span>
            <div className={`w-8 h-8 bg-white/20 rounded-xl flex items-center justify-center ${
              loadingCheckIn ? 'animate-pulse' : ''
            }`}>
              <MapPin className="w-4 h-4" />
            </div>
          </button>
        </div>

        {/* 主按钮 */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-fab transition-all duration-300 ease-out active:scale-90 touch-manipulation select-none pointer-events-auto ${
            isOpen
              ? 'bg-slate-700 rotate-45 shadow-slate-700/30'
              : 'bg-primary'
          }`}
          aria-label={isOpen ? '关闭菜单' : '打开快捷操作'}
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <X className="w-6 h-6 text-white" />
          ) : (
            <Zap className="w-6 h-6 text-white" />
          )}
        </button>
      </div>
    </>
  );
};
