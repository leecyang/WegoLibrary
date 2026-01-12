import { useState, useEffect } from 'react';
import { StatusTab } from '../components/StatusTab';
import { ConfigTab } from '../components/ConfigTab';
import { BottomNav, type TabType } from '../components/BottomNav';
import { FloatingActions } from '../components/FloatingActions';
import { getStatus, type StatusData } from '../lib/api';
import { Library, LogOut, Settings } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

function Home() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('status');
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const fetchStatus = async () => {
    try {
      const data = await getStatus();
      setStatus(data);
    } catch (error) {
      console.error('获取状态失败', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="fixed inset-0 flex flex-col bg-slate-50 overflow-hidden">
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
        {activeTab === 'config' && <ConfigTab currentData={status} onUpdate={fetchStatus} />}
      </main>

      {/* Floating Action Button */}
      <FloatingActions onUpdate={fetchStatus} autoCheckinEnabled={!!status?.auto_checkin_enabled} />

      {/* Bottom Navigation */}
      <BottomNav activeTab={activeTab} onChange={setActiveTab} />
    </div>
  );
}

export default Home;
