'use client';
import { useCallback, useEffect, useState } from 'react';
import { rssRelayApi } from './api';
import type { PostInfo } from './types';

export function usePosts(limit = 50) {
  const [posts, setPosts] = useState<PostInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await rssRelayApi.getPosts(limit);
      setPosts(res.posts);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { posts, loading, error, refresh };
}

/** ISO 8601 → "2026-07-02 22:57" */
export function formatTime(iso: string): string {
  if (!iso) return '未知';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
