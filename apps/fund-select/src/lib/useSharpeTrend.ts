/**
 * 夏普走势取数 hook（夏普走势独立页 + 走势弹框共用）
 *
 * - code/range/重试计数变化都中止旧请求（AbortController），防旧响应覆盖新状态
 * - code 为 null 时不发请求（弹框未打开 / 独立页还没输代码）
 * - 区间切换时保留旧数据（data 不清空），加载骨架只在「无数据 + 加载中」时出现
 */
'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  DEFAULT_TREND_RANGE,
  fetchSharpeTrend,
  type SharpeTrendRange,
  type SharpeTrendResponse,
} from './sharpe-trend';

export interface UseSharpeTrendResult {
  data: SharpeTrendResponse | null;
  loading: boolean;
  error: string | null;
  /** 重新拉取（错误态「重试」按钮） */
  reload: () => void;
}

export function useSharpeTrend(
  code: string | null,
  range: SharpeTrendRange = DEFAULT_TREND_RANGE,
): UseSharpeTrendResult {
  const [data, setData] = useState<SharpeTrendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    if (!code) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchSharpeTrend(code, range, controller.signal)
      .then(res => {
        if (controller.signal.aborted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : '请求失败，请重试');
        setLoading(false);
      });
    return () => controller.abort();
  }, [code, range, reloadTick]);

  const reload = useCallback(() => setReloadTick(t => t + 1), []);

  return { data, loading, error, reload };
}
