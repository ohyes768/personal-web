import { directClient } from './api-client';
import type { PostsResponse } from './types';

export const rssRelayApi = {
  /** 拉取 post 列表（默认 50 条，最多 200）
   *
   * 注意：basePath='/rss' 时，浏览器调 `/api/...` 实际命中的是 `/rss/api/...`，
   * 因为 Next.js App Router 把 basePath 同时作用于 pages 和 API routes。
   */
  getPosts: (limit = 50) =>
    directClient.get<PostsResponse>('/rss/api/rss-relay/posts', { limit }),
};
