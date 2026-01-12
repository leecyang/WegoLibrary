import React, { useState } from 'react';
import { MapPin, RefreshCw } from 'lucide-react';
import { triggerCheckIn, enableAutoCheckIn, disableAutoCheckIn } from '../lib/api';

interface Props {
  onUpdate: () => void;
  autoCheckinEnabled?: boolean;
}

export const ActionButtons: React.FC<Props> = ({ onUpdate, autoCheckinEnabled = false }) => {
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
    } catch {
      showFeedback('danger', '签到失败');
    } finally {
      setLoadingCheckIn(false);
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
    }
  };

  return (
    <>
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

      <div className="grid grid-cols-2 gap-3 w-full">
      <button 
        onClick={handleToggleAutoCheckin}
        disabled={loadingAutoCheckin}
        className={`glass-card p-4 flex flex-col items-center justify-center gap-2 hover:bg-white/90 active:bg-white/95 transition-all active:scale-95 group touch-manipulation ${
          autoCheckinEnabled ? 'text-[#dc3545] hover:text-[#dc3545]' : 'text-slate-600 hover:text-primary'
        }`}
      >
        <div className={`p-2.5 rounded-full bg-slate-100 transition-colors ${loadingAutoCheckin ? 'animate-spin' : ''} ${
          autoCheckinEnabled ? 'group-hover:bg-red-50' : 'group-hover:bg-blue-50'
        }`}>
          <RefreshCw className="w-5 h-5" />
        </div>
        <span className="text-sm font-medium">{autoCheckinEnabled ? '关闭补签' : '开启补签'}</span>
      </button>

      <button 
        onClick={handleCheckIn}
        disabled={loadingCheckIn}
        className="glass-card p-4 flex flex-col items-center justify-center gap-2 hover:bg-white/90 active:bg-white/95 transition-all active:scale-95 text-slate-600 hover:text-cta group touch-manipulation"
      >
        <div className={`p-2.5 rounded-full bg-slate-100 group-hover:bg-orange-50 transition-colors ${loadingCheckIn ? 'animate-bounce' : ''}`}>
          <MapPin className="w-5 h-5" />
        </div>
        <span className="text-sm font-medium">立即签到</span>
      </button>
      </div>
    </>
  );
};
