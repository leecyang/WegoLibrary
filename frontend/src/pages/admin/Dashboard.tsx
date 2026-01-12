import { useState, useEffect } from 'react';
import { getAdminUsers, deleteAdminUser, adminTriggerCheckIn } from '../../lib/api';
import type { AdminUserConfig } from '../../lib/api';
import { Trash2, PlayCircle, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function AdminDashboard() {
  const [users, setUsers] = useState<AdminUserConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchUsers = async () => {
    try {
      const data = await getAdminUsers();
      setUsers(data);
    } catch (error) {
      console.error('获取用户列表失败', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleDelete = async (userId: number) => {
    if (!window.confirm('确定要删除该用户吗？此操作不可恢复。')) return;
    try {
      await deleteAdminUser(userId);
      setUsers(users.filter(u => u.user_id !== userId));
    } catch (error) {
      alert('删除失败');
    }
  };

  const handleTrigger = async (userId: number) => {
    try {
      await adminTriggerCheckIn(userId);
      alert('触发成功');
      fetchUsers(); // 刷新状态
    } catch (error: any) {
      alert(error.response?.data?.detail || '触发失败');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate('/')}
              className="p-2 bg-white rounded-lg shadow-sm hover:bg-slate-50 text-slate-600"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-2xl font-bold text-slate-800">管理员后台</h1>
          </div>
          <div className="text-sm text-slate-500">
            共 {users.length} 位用户
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-slate-500">加载中...</div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-100">
                  <tr>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600">ID</th>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600">用户名</th>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600">配置状态</th>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600">运行状态</th>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600">最后签到</th>
                    <th className="px-6 py-4 text-sm font-semibold text-slate-600 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((user) => (
                    <tr key={user.user_id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-4 text-sm text-slate-500">#{user.user_id}</td>
                      <td className="px-6 py-4 text-sm font-medium text-slate-800">{user.username}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          user.is_configured 
                            ? 'bg-green-50 text-green-700' 
                            : 'bg-slate-100 text-slate-600'
                        }`}>
                          {user.is_configured ? '已配置' : '未配置'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">{user.status}</td>
                      <td className="px-6 py-4 text-sm text-slate-500">{user.last_checkin}</td>
                      <td className="px-6 py-4 text-right flex justify-end gap-2">
                        <button
                          onClick={() => handleTrigger(user.user_id)}
                          disabled={!user.is_configured}
                          className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
                          title="强制签到"
                        >
                          <PlayCircle className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(user.user_id)}
                          className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title="删除用户"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {users.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-sm">
                        暂无用户
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
