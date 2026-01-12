import React from 'react';
import { Activity, Settings2 } from 'lucide-react';

export type TabType = 'status' | 'config';

interface Props {
  activeTab: TabType;
  onChange: (tab: TabType) => void;
}

const tabs = [
  { id: 'status' as TabType, label: '状态', icon: Activity },
  { id: 'config' as TabType, label: '配置', icon: Settings2 },
];

export const BottomNav: React.FC<Props> = ({ activeTab, onChange }) => {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-100 safe-area-bottom z-40">
      <div className="max-w-md mx-auto grid grid-cols-2 h-16">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`relative flex flex-col items-center justify-center gap-0.5 touch-target touch-manipulation select-none transition-colors duration-200 ${
                isActive ? 'text-primary' : 'text-slate-400 active:text-slate-600'
              }`}
              aria-label={tab.label}
              aria-current={isActive ? 'page' : undefined}
            >
              {/* 选中指示器 */}
              <div className={`absolute top-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full transition-all duration-200 ${
                isActive ? 'bg-primary' : 'bg-transparent'
              }`} />

              {/* 图标容器 */}
              <div className={`p-1.5 rounded-xl transition-all duration-200 ${
                isActive ? 'bg-primary-light' : ''
              }`}>
                <Icon className={`w-5 h-5 transition-transform duration-200 ${
                  isActive ? 'scale-105' : ''
                }`} strokeWidth={isActive ? 2.5 : 2} />
              </div>

              {/* 标签 */}
              <span className={`text-[11px] font-medium transition-colors duration-200 ${
                isActive ? 'text-primary' : 'text-slate-500'
              }`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
