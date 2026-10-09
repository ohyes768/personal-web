import { directClient } from './api-client';
import type { Channel, PostsResponse } from './types';

export const rssRelayApi = {
  getChannels: (includeDisabled = false) => directClient.get<{ channels: Channel[] }>(
    '/rss/api/rss-relay/channels', includeDisabled ? { include_disabled: 'true' } : undefined),
  createChannel: (channel: Pick<Channel, 'id' | 'title' | 'description'>) =>
    directClient.mutate<Channel>('/rss/api/rss-relay/channels', 'POST', channel),
  updateChannel: (id: string, updates: Partial<Pick<Channel, 'title' | 'description' | 'enabled'>>) =>
    directClient.mutate<Channel>(`/rss/api/rss-relay/channels/${encodeURIComponent(id)}`, 'PATCH', updates),
  /** 拉取 post 列表（默认 50 条，最多 200）
   *
   * 注意：basePath='/rss' 时，浏览器调 `/api/...` 实际命中的是 `/rss/api/...`，
   * 因为 Next.js App Router 把 basePath 同时作用于 pages 和 API routes。
   */
  getPosts: (limit = 50, channel?: string) =>
    directClient.get<PostsResponse>('/rss/api/rss-relay/posts', { limit, ...(channel ? { channel } : {}) }),

  /** 删除一篇 post。404 时 throw，调用方 catch。 */
  deletePost: (id: string) =>
    directClient.delete(
      `/rss/api/rss-relay/posts/${encodeURIComponent(id)}`
    ),
};
