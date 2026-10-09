export const PUBLIC_API = 'https://web.duomi77.cn:9443/rss/api/rss-relay';
export function feedUrl(channel?: string, token = process.env.NEXT_PUBLIC_RSS_TOKEN || '') {
  const params = new URLSearchParams({ token });
  if (channel) params.set('channel', channel);
  return `${PUBLIC_API}/rss.xml?${params}`;
}
export function pushExample(channel: string) {
  return JSON.stringify({ title: '今日内容', content: '# 今日内容\n\n正文 markdown', channel, source: 'my-bot', url: '' }, null, 2);
}
