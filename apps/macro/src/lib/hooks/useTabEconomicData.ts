/**
 * 按 Tab 拉取经济数据 — 切换 Tab 时请求 /api/macro/data/{tab}，按 Tab 缓存
 * timeRange 变化仅走 useFilteredEconomicData 本地切片，不再发请求
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

const TAB_CACHE_KEY_PREFIX = 'economic_tab_data_cache:';
const CACHE_TTL_MS = 3600000;

function readTabCache(tab: ChartTabType): EconomicDataResponse | null {
  try {
    const raw = localStorage.getItem(`${TAB_CACHE_KEY_PREFIX}${tab}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { data: EconomicDataResponse; timestamp: number };
    if (Date.now() - parsed.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(`${TAB_CACHE_KEY_PREFIX}${tab}`);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

function writeTabCache(tab: ChartTabType, data: EconomicDataResponse): void {
  try {
    localStorage.setItem(
      `${TAB_CACHE_KEY_PREFIX}${tab}`,
      JSON.stringify({ data, timestamp: Date.now() })
    );
  } catch (e) {
    console.warn('Tab 数据 localStorage 写入失败:', e);
  }
}

function clearTabCache(tab: ChartTabType): void {
  localStorage.removeItem(`${TAB_CACHE_KEY_PREFIX}${tab}`);
}

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

  const invalidateTab = useCallback((tab?: ChartTabType) => {
    const target = tab ?? chartTab;
    if (!target) return;
    clearTabCache(target);
    setTabDataMap((prev) => {
      const next = { ...prev };
      delete next[target];
      return next;
    });
  }, [chartTab]);

  useEffect(() => {
    if (!chartTab) {
      setIsLoading(false);
      setError(null);
      setIsCached(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      let forceRefetch = false;

      // refreshKey 变化：清当前 Tab 缓存后重拉
      if (refreshKey !== lastRefreshKeyRef.current) {
        lastRefreshKeyRef.current = refreshKey;
        forceRefetch = true;
        clearTabCache(chartTab);
        setTabDataMap((prev) => {
          const next = { ...prev };
          delete next[chartTab];
          return next;
        });
      }

      // 内存缓存命中（手动刷新后 forceRefetch 跳过，避免闭包里的旧 tabDataMap 误判）
      if (!forceRefetch && tabDataMap[chartTab]) {
        setIsLoading(false);
        setError(null);
        setIsCached(false);
        return;
      }

      // localStorage 缓存命中（仅 refreshKey 未变时）
      if (!forceRefetch && refreshKey === 0) {
        const cached = readTabCache(chartTab);
        if (cached) {
          setTabDataMap((prev) => ({ ...prev, [chartTab]: cached }));
          setIsLoading(false);
          setError(null);
          setIsCached(true);
          return;
        }
      }

      if (inflightRef.current === chartTab) return;
      inflightRef.current = chartTab;
      setIsLoading(true);
      setError(null);
      setIsCached(false);

      try {
        const response = await economicApi.getTabData(chartTab);
        if (!cancelled) {
          setTabDataMap((prev) => ({ ...prev, [chartTab]: response }));
          writeTabCache(chartTab, response);
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

  const fullData = chartTab ? tabDataMap[chartTab] ?? null : null;

  return { tabDataMap, fullData, isLoading, error, isCached, invalidateTab };
}
