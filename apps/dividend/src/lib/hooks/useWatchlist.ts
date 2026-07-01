/**
 * useWatchlist — 收藏股票 Hook
 *
 * 状态：Set<string>（O(1) 查询 has）
 * 乐观更新：toggle 后立即改本地状态，失败回滚 + alert
 * 跨 tab 同步：监听 'storage' 事件，跨浏览器 tab 状态共享
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  getFavorites,
  addFavorite,
  removeFavorite,
  type FavoriteItem,
} from '@/lib/watchlist';

export interface UseWatchlistResult {
  /** O(1) 查询的 codes Set */
  codes: Set<string>;
  /** 收藏详情列表（带 added_at / note） */
  items: FavoriteItem[];
  /** 收藏总数 */
  total: number;
  /** 首次加载中 */
  loading: boolean;
  /** code 是否在收藏中 */
  has: (code: string) => boolean;
  /** 切换收藏：已收藏则移除，未收藏则添加 */
  toggle: (code: string) => Promise<void>;
  /** 手动刷新（多 tab 同步用） */
  refresh: () => Promise<void>;
}

export function useWatchlist(): UseWatchlistResult {
  const [codes, setCodes] = useState<Set<string>>(new Set());
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await getFavorites();
      setCodes(new Set(data.codes));
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error('获取收藏列表失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // 启动时拉一次
  useEffect(() => {
    refresh();
  }, [refresh]);

  // 跨 tab 同步：监听 storage 事件（任意 tab 改了 favorites.json 后，其他 tab GET 会拿到新值）
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === null || e.key === 'watchlist-sync-tick') {
        // 任意 key 变更或被清空都触发一次拉取
        refresh();
      }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, [refresh]);

  const has = useCallback((code: string) => codes.has(code), [codes]);

  const toggle = useCallback(async (code: string) => {
    const wasInSet = codes.has(code);
    // 乐观更新
    setCodes(prev => {
      const next = new Set(prev);
      if (wasInSet) next.delete(code);
      else next.add(code);
      return next;
    });
    setTotal(prev => wasInSet ? prev - 1 : prev + 1);

    try {
      if (wasInSet) {
        await removeFavorite(code);
      } else {
        await addFavorite(code);
      }
      // 触发 storage 事件让其他 tab 同步（即使不跨 tab 也能确保 items 列表的 added_at 准确）
      localStorage.setItem('watchlist-sync-tick', String(Date.now()));
      // 本 tab 拉一次最新 items
      refresh();
    } catch (err) {
      // 回滚
      setCodes(prev => {
        const next = new Set(prev);
        if (wasInSet) next.add(code);
        else next.delete(code);
        return next;
      });
      setTotal(prev => wasInSet ? prev + 1 : prev - 1);
      const msg = err instanceof Error ? err.message : '操作失败';
      alert(`收藏操作失败：${msg}`);
    }
  }, [codes, refresh]);

  return { codes, items, total, loading, has, toggle, refresh };
}
