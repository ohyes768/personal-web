export interface PostInfo {
  id: string;
  title: string;
  url: string;
  source: string;
  created_at: string;        // ISO 8601
  content: string;           // markdown 原文
  preview: string;           // 200 字摘要
}

export interface PostsResponse {
  total: number;
  posts: PostInfo[];
}
