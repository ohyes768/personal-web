'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { rssRelayApi } from './api';
import type { PostInfo } from './types';

export function usePosts(limit = 50, channel?: string, enabled = true) {
  const key = `${limit}:${channel || ''}`;
  const currentKey = useRef(key);
  currentKey.current = key;
  const generation = useRef(0);
  const [result, setResult] = useState<{ key: string; posts: PostInfo[]; loading: boolean; error: string | null }>({ key, posts: [], loading: true, error: null });

  const refresh = useCallback(async () => {
    if (!enabled || currentKey.current !== key) return;
    const requestGeneration = ++generation.current;
    setResult({ key, posts: [], loading: true, error: null });
    try {
      const res = await rssRelayApi.getPosts(limit, channel);
      if (generation.current === requestGeneration && currentKey.current === key)
        setResult({ key, posts: res.posts, loading: false, error: null });
    } catch (e) {
      if (generation.current === requestGeneration && currentKey.current === key)
        setResult({ key, posts: [], loading: false, error: e instanceof Error ? e.message : '加载失败' });
    }
  }, [limit, channel, enabled, key]);

  useEffect(() => {
    void refresh();
    return () => { generation.current++; };
  }, [refresh]);

  const visible = enabled && result.key === key ? result : { posts: [], loading: true, error: null };
  return { ...visible, refresh };
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
