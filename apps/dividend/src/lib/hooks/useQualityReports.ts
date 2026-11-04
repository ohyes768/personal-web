/**
 * useQualityReports — 只读加载已保存的基本面评级结果
 *
 * 与 useQualityAnalysis 分离：不发现/轮询分析任务，不提交分析，只读取全量结果。
 * 首次失败不伪装成空列表；手动刷新失败保留旧快照。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendApi } from '@/lib/api';
import type { QualityScoresResponse } from '@/lib/quality';

export interface QualityReportsState {
  /** 最近一次成功读取的完整响应（刷新失败时保留） */
  snapshot: QualityScoresResponse | null;
  /** 首次加载中 */
  loading: boolean;
  /** 手动刷新中 */
  refreshing: boolean;
  /** 最近一次失败原因；null 表示无错误 */
  error: string | null;
  /** 手动刷新 */
  refresh: () => Promise<void>;
}

export function useQualityReports(): QualityReportsState {
  const [snapshot, setSnapshot] = useState<QualityScoresResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const mounted = useRef(true);

  const load = useCallback(async (mode: 'initial' | 'manual') => {
    const seq = ++requestSeq.current;
    if (mode === 'manual') setRefreshing(true);
    else setLoading(true);
    try {
      const response = await dividendApi.getQualityScores();
      // 迟到的旧响应不得覆盖新请求
      if (!mounted.current || seq !== requestSeq.current) return;
      setSnapshot(response);
      setError(null);
    } catch (err) {
      if (!mounted.current || seq !== requestSeq.current) return;
      setError(err instanceof Error ? err.message : '基本面资料加载失败');
    } finally {
      if (mounted.current && seq === requestSeq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load('initial');
    return () => { mounted.current = false; };
  }, [load]);

  const refresh = useCallback(async () => { await load('manual'); }, [load]);

  return { snapshot, loading, refreshing, error, refresh };
}
