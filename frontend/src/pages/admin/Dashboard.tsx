import { useState, useEffect } from 'react';
import type { AxiosError } from 'axios';
import {
  getAdminUsers,
  deleteAdminUser,
  adminTriggerCheckIn,
  getAdminAnnouncement,
  updateAdminAnnouncementDraft,
  publishAdminAnnouncement,
  unpublishAdminAnnouncement,
} from '../../lib/api';
import type { AdminUserConfig, AdminAnnouncementData } from '../../lib/api';
import {
  Trash2,
  PlayCircle,
  ArrowLeft,
  Megaphone,
  Save,
  Send,
  EyeOff,
  CalendarClock,
  FileText,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AnnouncementMarkdown } from '../../components/AnnouncementMarkdown';

export default function AdminDashboard() {
  const [users, setUsers] = useState<AdminUserConfig[]>([]);
  const [announcement, setAnnouncement] = useState<AdminAnnouncementData | null>(null);
  const [draftContent, setDraftContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [announcementAction, setAnnouncementAction] = useState<'save' | 'publish' | 'unpublish' | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const navigate = useNavigate();

  const syncAnnouncementState = (data: AdminAnnouncementData) => {
    setAnnouncement(data);
    setDraftContent(data.draft_content);
  };

  const getErrorMessage = (error: unknown, fallback: string) => {
    const axiosError = error as AxiosError<{ detail?: string }>;
    return axiosError.response?.data?.detail || fallback;
  };

  const showMessage = (next: { type: 'success' | 'error'; text: string }) => {
    setMessage(next);
    window.setTimeout(() => setMessage(null), 3000);
  };

  const fetchUsers = async () => {
    const data = await getAdminUsers();
    setUsers(data);
  };

  const fetchAnnouncement = async () => {
    const data = await getAdminAnnouncement();
    syncAnnouncementState(data);
  };

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        await Promise.all([fetchUsers(), fetchAnnouncement()]);
      } catch (error) {
        console.error('获取管理后台数据失败', error);
        showMessage({ type: 'error', text: getErrorMessage(error, '加载管理后台数据失败') });
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
  }, []);

  const handleDelete = async (userId: number) => {
    if (!window.confirm('确定要删除该用户吗？此操作不可恢复。')) return;
    try {
      await deleteAdminUser(userId);
      setUsers((prev) => prev.filter((user) => user.user_id !== userId));
      showMessage({ type: 'success', text: '用户已删除' });
    } catch (error) {
      showMessage({ type: 'error', text: getErrorMessage(error, '删除失败') });
    }
  };

  const handleTrigger = async (userId: number) => {
    try {
      await adminTriggerCheckIn(userId);
      showMessage({ type: 'success', text: '已触发签到' });
      fetchUsers();
    } catch (error) {
      showMessage({ type: 'error', text: getErrorMessage(error, '触发失败') });
    }
  };

  const handleSaveAnnouncement = async () => {
    setAnnouncementAction('save');
    try {
      const data = await updateAdminAnnouncementDraft({ content: draftContent });
      syncAnnouncementState(data);
      showMessage({ type: 'success', text: '公告草稿已保存' });
    } catch (error) {
      showMessage({ type: 'error', text: getErrorMessage(error, '保存草稿失败') });
    } finally {
      setAnnouncementAction(null);
    }
  };

  const handlePublishAnnouncement = async () => {
    setAnnouncementAction('publish');
    try {
      const data = await publishAdminAnnouncement();
      syncAnnouncementState(data);
      showMessage({ type: 'success', text: '公告已发布' });
    } catch (error) {
      showMessage({ type: 'error', text: getErrorMessage(error, '发布失败') });
    } finally {
      setAnnouncementAction(null);
    }
  };

  const handleUnpublishAnnouncement = async () => {
    if (!window.confirm('确定要撤下当前已发布公告吗？')) return;
    setAnnouncementAction('unpublish');
    try {
      const data = await unpublishAdminAnnouncement();
      syncAnnouncementState(data);
      showMessage({ type: 'success', text: '公告已撤下' });
    } catch (error) {
      showMessage({ type: 'error', text: getErrorMessage(error, '撤下公告失败') });
    } finally {
      setAnnouncementAction(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4 sm:p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
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

        {message && (
          <div className={`rounded-xl border px-4 py-3 flex items-center gap-3 ${
            message.type === 'success'
              ? 'bg-white border-green-100 text-green-700'
              : 'bg-white border-red-100 text-red-700'
          }`}>
            {message.type === 'success'
              ? <CheckCircle2 className="w-5 h-5 shrink-0" />
              : <AlertCircle className="w-5 h-5 shrink-0" />}
            <span className="text-sm font-medium">{message.text}</span>
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-slate-500">加载中...</div>
        ) : (
          <>
            <section className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
              <div className="px-6 py-5 border-b border-slate-100 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded-2xl bg-primary-light flex items-center justify-center">
                    <Megaphone className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-slate-800">公告设置</h2>
                    <p className="text-sm text-slate-500">保存草稿后可手动发布，普通用户首页只展示当前已发布公告。</p>
                  </div>
                </div>
                <div className={announcement?.is_published ? 'status-badge-success' : 'status-badge-neutral'}>
                  {announcement?.is_published ? '已发布' : '未发布'}
                </div>
              </div>

              <div className="p-6 grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <label className="text-sm font-semibold text-slate-700">公告正文</label>
                    <span className="text-xs text-slate-400">{draftContent.length}/2000</span>
                  </div>
                  <textarea
                    value={draftContent}
                    onChange={(event) => setDraftContent(event.target.value)}
                    maxLength={2000}
                    rows={10}
                    placeholder="输入要发布给全站用户的公告内容..."
                    className="input-field min-h-[240px] resize-y text-sm leading-7"
                  />
                  <div className="text-xs text-slate-500">
                    支持 Markdown 语法和普通换行。保存草稿不会立即影响线上公告，右侧会按最终样式预览。
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={handleSaveAnnouncement}
                      disabled={announcementAction !== null}
                      className="btn-secondary flex items-center gap-2"
                    >
                      <Save className="w-4 h-4" />
                      {announcementAction === 'save' ? '保存中...' : '保存草稿'}
                    </button>
                    <button
                      onClick={handlePublishAnnouncement}
                      disabled={announcementAction !== null}
                      className="btn-primary flex items-center gap-2"
                    >
                      <Send className="w-4 h-4" />
                      {announcementAction === 'publish' ? '发布中...' : '发布公告'}
                    </button>
                    <button
                      onClick={handleUnpublishAnnouncement}
                      disabled={announcementAction !== null || !announcement?.is_published}
                      className="px-4 py-2.5 rounded-xl font-medium text-red-600 bg-red-50 hover:bg-red-100 active:scale-[0.97] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 flex items-center gap-2"
                    >
                      <EyeOff className="w-4 h-4" />
                      {announcementAction === 'unpublish' ? '撤下中...' : '撤下公告'}
                    </button>
                  </div>
                </div>

                <div className="space-y-5">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <CalendarClock className="w-4 h-4 text-slate-500" />
                      发布状态
                    </div>
                    <div className="flex items-center justify-between gap-4 text-sm">
                      <span className="text-slate-500">当前状态</span>
                      <span className="font-medium text-slate-800">{announcement?.is_published ? '已发布' : '未发布'}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4 text-sm">
                      <span className="text-slate-500">最近编辑</span>
                      <span className="font-medium text-slate-800 text-right">{announcement?.updated_at || '尚未保存'}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4 text-sm">
                      <span className="text-slate-500">发布时间</span>
                      <span className="font-medium text-slate-800 text-right">{announcement?.published_at || '未发布'}</span>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <FileText className="w-4 h-4 text-slate-500" />
                      草稿预览
                    </div>
                    <div className="mt-3 min-h-[160px] rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                      {draftContent.trim()
                        ? <AnnouncementMarkdown content={draftContent} />
                        : <div className="text-sm text-slate-500">当前草稿为空。</div>}
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <FileText className="w-4 h-4 text-slate-500" />
                      当前线上公告
                    </div>
                    <div className="mt-3 min-h-[160px] rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                      {announcement?.is_published && announcement.published_content
                        ? <AnnouncementMarkdown content={announcement.published_content} />
                        : <div className="text-sm text-slate-500">当前没有已发布公告。</div>}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section className="bg-white rounded-xl shadow-sm overflow-hidden border border-slate-100">
              <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between gap-4">
                <h2 className="text-lg font-semibold text-slate-800">用户管理</h2>
                <div className="text-sm text-slate-500">共 {users.length} 位用户</div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="bg-slate-50 border-b border-slate-100">
                    <tr>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">ID</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">用户名</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">微信昵称</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">姓名/学号</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">校区</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">配置状态</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">运行状态</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600">最后签到</th>
                      <th className="px-4 py-4 text-sm font-semibold text-slate-600 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.map((user) => {
                      const profileLabel =
                        user.profile_display === 'ready'
                          ? null
                          : user.profile_display === 'pending'
                            ? '待重新授权'
                            : '—';
                      const nameNo = [user.wechat_student_name, user.wechat_student_no]
                        .filter(Boolean)
                        .join(' / ');

                      return (
                      <tr key={user.user_id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-4 py-4 text-sm text-slate-500">#{user.user_id}</td>
                        <td className="px-4 py-4 text-sm font-medium text-slate-800">{user.username}</td>
                        <td className="px-4 py-4 text-sm text-slate-600">
                          {user.profile_display === 'ready' && user.wechat_avatar ? (
                            <div className="flex items-center gap-2">
                              <img
                                src={user.wechat_avatar}
                                alt=""
                                className="w-6 h-6 rounded-full object-cover border border-slate-200"
                              />
                              <span className="truncate max-w-[100px]">{user.wechat_nick || '—'}</span>
                            </div>
                          ) : (
                            <span className="text-slate-400">{profileLabel ?? user.wechat_nick ?? '—'}</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-sm text-slate-500 max-w-[120px] truncate">
                          {user.profile_display === 'ready' ? (nameNo || '—') : profileLabel ?? '—'}
                        </td>
                        <td className="px-4 py-4 text-sm text-slate-500 max-w-[100px] truncate">
                          {user.profile_display === 'ready' ? (user.wechat_sch || '—') : profileLabel ?? '—'}
                        </td>
                        <td className="px-4 py-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            user.is_configured
                              ? 'bg-green-50 text-green-700'
                              : 'bg-slate-100 text-slate-600'
                          }`}>
                            {user.is_configured ? '已配置' : '未配置'}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-sm text-slate-500">{user.status}</td>
                        <td className="px-4 py-4 text-sm text-slate-500 whitespace-nowrap">{user.last_checkin}</td>
                        <td className="px-4 py-4 text-right">
                          <div className="flex justify-end gap-2">
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
                          </div>
                        </td>
                      </tr>
                    );
                    })}
                    {users.length === 0 && (
                      <tr>
                        <td colSpan={9} className="px-6 py-12 text-center text-slate-400 text-sm">
                          暂无用户
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
