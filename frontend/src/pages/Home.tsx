import { useEffect, useState } from 'react';
import { StatusTab } from '../components/StatusTab';
import { ConfigTab } from '../components/ConfigTab';
import { BottomNav, type TabType } from '../components/BottomNav';
import { FloatingActions } from '../components/FloatingActions';
import { AnnouncementOverlay } from '../components/AnnouncementOverlay';
import { getStatus, getAnnouncement, type StatusData, type AnnouncementData } from '../lib/api';
import { BellRing, Library, LogOut, Settings } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

const ANNOUNCEMENT_LAST_SHOWN_KEY_PREFIX = 'announcement-last-shown-date';

function getAnnouncementStorageKey(username?: string) {
  return `${ANNOUNCEMENT_LAST_SHOWN_KEY_PREFIX}:${username || 'guest'}`;
}

function getTodayString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getLastAnnouncementShownDate(username?: string) {
  try {
    return localStorage.getItem(getAnnouncementStorageKey(username));
  } catch {
    return null;
  }
}

function markAnnouncementShownToday(username?: string) {
  try {
    localStorage.setItem(getAnnouncementStorageKey(username), getTodayString());
  } catch {
    // Ignore storage write failures and fall back to current-session behavior.
  }
}

function Home() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [announcement, setAnnouncement] = useState<AnnouncementData | null>(null);
  const [isAnnouncementOpen, setIsAnnouncementOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('status');
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const fetchHomeData = async () => {
    const [statusResult, announcementResult] = await Promise.allSettled([
      getStatus(),
      getAnnouncement(),
    ]);

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    } else {
      console.error('获取状态失败', statusResult.reason);
    }

    if (announcementResult.status === 'fulfilled') {
      setAnnouncement(announcementResult.value);
      if (announcementResult.value.has_announcement) {
        const lastShownDate = getLastAnnouncementShownDate(user?.username);
        const today = getTodayString();
        if (lastShownDate !== today) {
          setIsAnnouncementOpen(true);
          markAnnouncementShownToday(user?.username);
        }
      } else {
        setIsAnnouncementOpen(false);
      }
    } else {
      console.error('获取公告失败', announcementResult.reason);
    }

    setLoading(false);
  };

  useEffect(() => {
    fetchHomeData();
    const interval = setInterval(fetchHomeData, 10000);
    return () => clearInterval(interval);
  }, [user?.username]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="fixed inset-0 flex flex-col bg-slate-50 overflow-hidden">
      <AnnouncementOverlay
        announcement={announcement}
        isOpen={isAnnouncementOpen}
        onMinimize={() => setIsAnnouncementOpen(false)}
      />

      {/* Header */}
      <header className="flex-shrink-0 px-6 py-4 bg-white border-b border-slate-100 z-10">
        <div className="max-w-md mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 bg-primary rounded-2xl shadow-lg shadow-primary/25 flex items-center justify-center">
              <Library className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-800 tracking-tight">图书馆助手</h1>
              <p className="text-xs text-slate-500 mt-0.5">你好, {user?.username}</p>
            </div>
          </div>
          <div className="flex gap-2">
            {announcement?.has_announcement && !isAnnouncementOpen && (
              <button
                onClick={() => setIsAnnouncementOpen(true)}
                className="p-2 text-slate-400 hover:text-primary transition-colors"
                title="查看站点公告"
                aria-label="查看站点公告"
              >
                <BellRing className="w-5 h-5" />
              </button>
            )}
            {user?.is_admin && (
              <button
                onClick={() => navigate('/admin')}
                className="p-2 text-slate-400 hover:text-primary transition-colors"
                title="管理员后台"
              >
                <Settings className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={handleLogout}
              className="p-2 text-slate-400 hover:text-red-500 transition-colors"
              title="退出登录"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden max-w-md mx-auto w-full relative">
        {activeTab === 'status' && <StatusTab data={status} loading={loading} />}
        {activeTab === 'config' && <ConfigTab currentData={status} onUpdate={fetchHomeData} />}
      </main>

      {/* Floating Action Button */}
      <FloatingActions onUpdate={fetchHomeData} autoCheckinEnabled={!!status?.auto_checkin_enabled} />

      {/* Bottom Navigation */}
      <BottomNav activeTab={activeTab} onChange={setActiveTab} />
    </div>
  );
}

export default Home;
