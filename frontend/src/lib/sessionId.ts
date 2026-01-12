/**
 * 从文本中提取 Session ID (32位十六进制字符串)
 */
export function extractSessionIdFromText(text: string): string | null {
  if (!text) return null;
  // 匹配 32 位十六进制字符串
  const match = text.match(/[a-f0-9]{32}/i);
  return match ? match[0] : null;
}
