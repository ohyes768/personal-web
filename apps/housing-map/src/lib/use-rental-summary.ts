'use client';

import { useEffect, useState } from 'react';
import {
  buildRentalSummaryPath,
  fetchRentalData,
  type RentalAreaBand,
  type RentalBedroomsFilter,
  type RentalSummaryData,
  type RentalSummaryEntry,
} from './rental-types';
import { indexSummaries } from './rental-dashboard';

export interface UseRentalSummaryResult {
  /** community_id -> 摘要；口径变化后未命中（加载中/失败）时为 null，展示层降级为全 '—' */
  summaries: Record<string, RentalSummaryEntry> | null;
  error: string | null;
  loading: boolean;
}

/**
 * 看板租金摘要 hook（GET /api/rentals/summary）。
 * - 口径（area_band/bedrooms）变化时以 AbortController 取消旧请求重新拉取；
 * - 卸载时 abort 清理；reloadKey 变化用于刷新任务终态后手动重拉。
 */
export function useRentalSummary(
  areaBand: RentalAreaBand,
  bedrooms: RentalBedroomsFilter,
  reloadKey = 0,
): UseRentalSummaryResult {
  const [state, setState] = useState<{
    key: string;
    data?: Record<string, RentalSummaryEntry>;
    error?: string;
  } | null>(null);
  const key = `${areaBand}|${bedrooms}|${reloadKey}`;

  useEffect(() => {
    const controller = new AbortController();
    fetchRentalData<RentalSummaryData>(buildRentalSummaryPath({ areaBand, bedrooms }), controller.signal)
      .then(data => {
        if (controller.signal.aborted) return;
        // 边界校验：summaries 必须是数组，异常响应按失败处理而不是让看板崩溃
        if (!Array.isArray(data.summaries)) {
          setState({ key, error: '租金数据响应异常' });
          return;
        }
        setState({ key, data: indexSummaries(data.summaries) });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ key, error: '租金数据暂不可用' });
      });
    return () => controller.abort();
  }, [areaBand, bedrooms, reloadKey, key]);

  const current = state && state.key === key ? state : null;
  return {
    summaries: current?.data ?? null,
    error: current?.error ?? null,
    loading: !current,
  };
}
