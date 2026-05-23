/** 格式化签到结果文案（去掉错误码括号、统一标点） */
export function formatCheckinResultMessage(raw: string): string {
  if (!raw) return '';

  return raw
    .replace(/签到失败\s*\(\d+\)\s*[:：]/g, '签到失败：')
    .replace(/签到失败\s*\(\d+\)\s*/g, '签到失败：')
    .replace(/^签到失败:\s*/, '签到失败：')
    .replace('签到成功:', '签到成功：')
    .replace('扫码成功', '到馆验证成功')
    .trim();
}

/** 签到卡片正文（去掉标题前缀，避免与「签到失败」标题重复） */
export function formatCheckinResultDetail(raw: string): string {
  return formatCheckinResultMessage(raw)
    .replace(/^签到失败[:：]\s*/, '')
    .replace(/^签到成功[:：]\s*/, '')
    .trim();
}

export type WechatConnectionStatus =
  | 'disconnected'
  | 'connected'
  | 'expired'
  | 'unauthorized';

export function getWechatConnectionBadge(status: WechatConnectionStatus | undefined) {
  switch (status) {
    case 'expired':
      return {
        className: 'status-badge-warning',
        label: '已过期',
      };
    case 'unauthorized':
      return {
        className: 'status-badge-danger',
        label: '未授权',
      };
    case 'connected':
      return {
        className: 'status-badge-success',
        label: '已连接',
      };
    default:
      return null;
  }
}
