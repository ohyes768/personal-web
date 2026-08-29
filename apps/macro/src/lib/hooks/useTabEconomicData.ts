/**
 * 按 Tab 拉取经济数据 — 切换 Tab 时请求 /api/macro/data/{tab}，内存缓存 5 分钟
 * timeRange 变化仅走 useFilteredEconomicData 本地切片，不再发请求
 * 对比页不在此请求（由 ComparisonTab 按 indicators 自拉）
 */
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { EconomicDataResponse, TabType } from '../types/economic';
import { economicApi } from '../modules/economic/api';

/** 走图表 Tab 数据 API 的 Tab（macro-signal 有独立接口） */
export type ChartTabType = Exclude<TabType, 'macro-signal'>;

export interface UseTabEconomicDataResult {
  /** 各 Tab 已加载的全量数据缓存 */
  tabDataMap: Partial<Record<ChartTabType, EconomicDataResponse>>;
  /** 当前 activeTab 的全量数据 */
  fullData: EconomicDataResponse | null;
  /** 当前 activeTab 是否正在加载 */
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
  invalidateTab: (tab?: ChartTabType) => void;
}

const MEMORY_TTL_MS = 5 * 60 * 1000;

type CacheEntry = { data: EconomicDataResponse; fetchedAt: number };

export function useTabEconomicData(
  activeTab: TabType,
  refreshKey: number = 0
): UseTabEconomicDataResult {
  const chartTab: ChartTabType | null =
    activeTab === 'macro-signal' ? null : activeTab;

  const [tabDataMap, setTabDataMap] = useState<
    Partial<Record<ChartTabType, EconomicDataResponse>>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCached, setIsCached] = useState(false);
  const lastRefreshKeyRef = useRef(refreshKey);
  const inflightRef = useRef<ChartTabType | null>(null);
  const cacheRef = useRef<Map<ChartTabType, CacheEntry>>(new Map());

  const invalidateTab = useCallback((tab?: ChartTabType) => {
    const target = tab ?? chartTab;
    if (!target) return;
    cacheRef.current.delete(target);
    setTabDataMap((prev) => {
      const next = { ...prev };
      delete next[target];
      return next;
    });
  }, [chartTab]);

  useEffect(() => {
    if (!chartTab || chartTab === 'comparison') {
      setIsLoading(false);
      setError(null);
      setIsCached(false);
      return;
    }

    const dataTab = chartTab;
    let cancelled = false;

    const load = async () => {
      let forceRefetch = false;

      // refreshKey 变化：只清当前 Tab 的内存 entry 后重拉
      if (refreshKey !== lastRefreshKeyRef.current) {
        lastRefreshKeyRef.current = refreshKey;
        forceRefetch = true;
        cacheRef.current.delete(dataTab);
        setTabDataMap((prev) => {
          const next = { ...prev };
          delete next[dataTab];
          return next;
        });
      }

      const entry = cacheRef.current.get(dataTab);
      const fresh = entry && Date.now() - entry.fetchedAt < MEMORY_TTL_MS;

      if (!forceRefetch && fresh) {
        setTabDataMap((prev) =>
          prev[dataTab] ? prev : { ...prev, [dataTab]: entry.data }
        );
        setIsLoading(false);
        setError(null);
        setIsCached(true);
        return;
      }

      if (inflightRef.current === dataTab) return;
      inflightRef.current = dataTab;
      setIsLoading(true);
      setError(null);
      setIsCached(false);

      try {
        const response = await economicApi.getTabData(dataTab);
        if (!cancelled) {
          cacheRef.current.set(dataTab, { data: response, fetchedAt: Date.now() });
          setTabDataMap((prev) => ({ ...prev, [dataTab]: response }));
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : '获取数据失败';
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          inflightRef.current = null;
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
    // tabDataMap 故意不作为依赖：仅在 activeTab / refreshKey 变化时拉取
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartTab, refreshKey]);

  const fullData = chartTab && chartTab !== 'comparison' ? tabDataMap[chartTab] ?? null : null;

  return { tabDataMap, fullData, isLoading, error, isCached, invalidateTab };
}
