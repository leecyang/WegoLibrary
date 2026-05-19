import { BellRing } from 'lucide-react';
import type { AnnouncementData } from '../lib/api';
import { AnnouncementMarkdown } from './AnnouncementMarkdown';

interface Props {
  announcement: AnnouncementData | null;
  isOpen: boolean;
  onMinimize: () => void;
}

export function AnnouncementOverlay({ announcement, isOpen, onMinimize }: Props) {
  if (!announcement?.has_announcement || !isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-slate-900/35 backdrop-blur-[2px]" onClick={onMinimize} />
      <div className="absolute left-4 right-4 top-20 mx-auto max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/20">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary-light">
              <BellRing className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <div className="text-base font-semibold text-slate-900">站点公告</div>
              <div className="mt-0.5 text-xs text-slate-500">
                {announcement.published_at ? `发布于 ${announcement.published_at}` : '最新通知'}
              </div>
            </div>
          </div>
        </div>

        <div className="max-h-[min(60vh,32rem)] overflow-y-auto px-5 py-4">
          <AnnouncementMarkdown content={announcement.content} />
        </div>

        <div className="flex justify-end border-t border-slate-100 px-5 py-4">
          <button onClick={onMinimize} className="btn-secondary">
            收起
          </button>
        </div>
      </div>
    </div>
  );
}
