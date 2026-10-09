export interface PostInfo {
  id: string;
  title: string;
  url: string;
  source: string;
  channel?: string;
  created_at: string;        // ISO 8601
  content: string;           // markdown 原文
  preview: string;           // 200 字摘要
}

export interface Channel {
  id: string;
  title: string;
  description: string;
  enabled: boolean;
}

export interface PostsResponse {
  total: number;
  posts: PostInfo[];
}
