/**
 * useAlertsStatus — 收藏挡位（四条价格线）状态 Hook
 *
 * 挡位钉钉推送与监控已移除（2026-11-14）：这里只负责四条价格线的读写，
 * 没有启停开关、没有手动推送检查。
 *
 * 状态：
 *   - status: AlertStatusResponse | null（所有股票的四条价格线）
 *   - 由 status 派生：alertMap（code → AlertStatusItem）O(1) 查询
 *
 * 行为：
 *   - 启动时拉一次 /favorites/alerts/status
 *   - setAlerts/clearAlerts 后自动 refresh
 *   - 监听 watchlist-sync-tick storage 事件，跨 tab 同步
 *   - 乐观更新：setAlerts 后立刻改本地 status，失败回滚 + refresh
 */
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getAlertsStatus,
  setAlerts as apiSetAlerts,
  clearAlerts as apiClearAlerts,
} from '@/lib/watchlist';
import type {
  AlertConfigRequest,
  AlertStatusItem,
  AlertStatusResponse,
} from '@/lib/types';

export interface UseAlertsStatusResult {
  /** 完整状态（来自 GET /favorites/alerts/status） */
  status: AlertStatusResponse | null;
  /** code → AlertStatusItem O(1) 查询 */
  alertMap: Map<string, AlertStatusItem>;
  loading: boolean;
  error: string | null;
  /** 手动刷新 */
  refresh: () => Promise<void>;
  /** 设置/更新单只股票挡位（乐观更新） */
  setAlerts: (code: string, body: AlertConfigRequest) => Promise<void>;
  /** 清除单只股票挡位 */
  clearAlerts: (code: string) => Promise<void>;
}

export function useAlertsStatus(): UseAlertsStatusResult {
  const [status, setStatus] = useState<AlertStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getAlertsStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取挡位状态失败';
      setError(msg);
      console.error('[useAlertsStatus] refresh error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 跨 tab 同步：watchlist 变更或 alerts 变更都触发
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === null || e.key === 'watchlist-sync-tick' || e.key === 'alerts-sync-tick') {
        refresh();
      }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, [refresh]);

  const triggerSync = () => {
    localStorage.setItem('alerts-sync-tick', String(Date.now()));
  };

  const setAlerts = useCallback(
    async (code: string, body: AlertConfigRequest) => {
      // 乐观更新：本地 status 先改
      const prev = status;
      if (prev) {
        setStatus({
          ...prev,
          items: prev.items.map(it =>
            it.code === code
              ? {
                  ...it,
                  // updated_at 由后端刷新后提供（带真时间戳），乐观更新时用 ISO 字符串占位
                  updated_at: new Date().toISOString(),
                  levels: body.levels,
                  has_levels:
                    !!body.levels.heavy_position ||
                    !!body.levels.add_position ||
                    !!body.levels.reduce_position ||
                    !!body.levels.full_exit,
                  level_count:
                    [body.levels.heavy_position, body.levels.add_position, body.levels.reduce_position, body.levels.full_exit].filter(
                      lv => !!lv
                    ).length,
                }
              : it
          ),
        });
      }
      try {
        await apiSetAlerts(code, body);
        triggerSync();
        // 拉最新服务器状态（拿真 updated_at 与 pb）
        await refresh();
      } catch (err) {
        // 回滚
        setStatus(prev);
        const msg = err instanceof Error ? err.message : '设置挡位失败';
        alert(`设置挡位失败：${msg}`);
        throw err;
      }
    },
    [status, refresh]
  );

  const clearAlerts = useCallback(
    async (code: string) => {
      const prev = status;
      if (prev) {
        setStatus({
          ...prev,
          items: prev.items.map(it =>
            it.code === code
              ? {
                  ...it,
                  levels: null,
                  has_levels: false,
                  level_count: 0,
                  updated_at: null,
                }
              : it
          ),
        });
      }
      try {
        await apiClearAlerts(code);
        triggerSync();
        await refresh();
      } catch (err) {
        setStatus(prev);
        const msg = err instanceof Error ? err.message : '清除挡位失败';
        alert(`清除挡位失败：${msg}`);
        throw err;
      }
    },
    [status, refresh]
  );

  const alertMap = useMemo(() => {
    const m = new Map<string, AlertStatusItem>();
    status?.items.forEach(it => m.set(it.code, it));
    return m;
  }, [status]);

  return { status, alertMap, loading, error, refresh, setAlerts, clearAlerts };
}
