/**
 * News 模块自定义 Hooks
 */
import { useState, useCallback } from 'react';
import { newsApi } from './api';
import type { PolicyRankingData, SentimentDistribution, HeatmapResponse } from './types';

/**
 * 政策推荐排行 Hook
 */
export function usePolicyRanking(timeRange: string = '1M', topN: number = 20) {
  const [data, setData] = useState<PolicyRankingData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await newsApi.getPolicyRanking(timeRange, topN);
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取政策排行失败';
      setError(message);
      console.error('获取政策排行失败:', err);
    } finally {
      setLoading(false);
    }
  }, [timeRange, topN]);

  return { data, loading, error, fetch, refetch: fetch };
}

/**
 * 情感分布 Hook
 */
export function useSentimentDistribution(timeRange: string = '1M') {
  const [data, setData] = useState<SentimentDistribution | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await newsApi.getSentimentDistribution(timeRange);
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取情感分布失败';
      setError(message);
      console.error('获取情感分布失败:', err);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  return { data, loading, error, fetch, refetch: fetch };
}

/**
 * 板块影响 Hook
 */
export function useSectorImpact() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (date: string) => {
    setLoading(true);
    setError(null);

    try {
      const result = await newsApi.getSectorImpact(date);
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取板块影响失败';
      setError(message);
      console.error('获取板块影响失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetch, refetch: fetch };
}

/**
 * 热力图 Hook
 */
export function useHeatmap() {
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (boardCode: string, timeRange: string = '1M') => {
    setLoading(true);
    setError(null);

    try {
      const result = await newsApi.getHeatmap(boardCode, timeRange);
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取热力图失败';
      setError(message);
      console.error('获取热力图失败:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetch, refetch: fetch };
}