/**
 * Economic 模块自定义 Hooks
 */
import { useState, useEffect } from 'react';
import { economicApi } from './api';
import type { TimeRange, EconomicDataResponse, TabType } from './types';

/**
 * 经济数据 Hook
 * 使用全量加载 + 本地过滤策略
 */
export function useEconomicData(timeRange: TimeRange, tabType: TabType = 'treasury-exchange') {
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [filteredData, setFilteredData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCached, setIsCached] = useState(false);

  const CACHE_KEY = 'economic_data_full_cache';
  const CACHE_DURATION = 3600000; // 1小时

  const getDefaultData = (): EconomicDataResponse => ({
    dates: [],
    us_treasuries: { '3m': [], '2y': [], '10y': [] },
    eu_treasuries: { '3m': [], '2y': [], '10y': [] },
    jp_treasuries: { '3m': [], '2y': [], '10y': [] },
    exchange_rates: {
      dollar_index: [],
      usd_cny: [],
      usd_jpy: [],
      usd_eur: [],
    },
    vix: [],
  });

  // 首次加载全量数据
  useEffect(() => {
    const fetchFullData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // 尝试从缓存读取
        const cached = localStorage.getItem(CACHE_KEY);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (Date.now() - parsed.timestamp < CACHE_DURATION && parsed.data) {
            setFullData(parsed.data);
            setIsCached(true);
            setIsLoading(false);
            return;
          }
          localStorage.removeItem(CACHE_KEY);
        }

        // 从API获取全量数据
        const response = await economicApi.getData('2000-01-01');
        setFullData(response);
        setIsCached(false);

        // 写入缓存
        localStorage.setItem(
          CACHE_KEY,
          JSON.stringify({
            data: response,
            timestamp: Date.now(),
          }),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : '获取数据失败';
        setError(message);
        console.error('获取经济数据失败:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchFullData();
  }, []);

  // 过滤数据（由页面组件调用，因为需要使用 utils 工具函数）
  // 这里只返回全量数据和过滤后的数据，具体过滤逻辑保留在页面或 hooks 中
  return {
    data: filteredData,
    fullData,
    isLoading,
    error,
    isCached,
    setFilteredData,
  };
}

/**
 * 数据更新 Hook
 */
export function useEconomicUpdate() {
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateData = async () => {
    setIsUpdating(true);
    setError(null);

    try {
      await economicApi.updateData();
      // 清除缓存，下次会重新获取数据
      localStorage.removeItem('economic_data_full_cache');
    } catch (err) {
      const message = err instanceof Error ? err.message : '更新失败';
      setError(message);
      console.error('更新经济数据失败:', err);
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  return {
    isUpdating,
    error,
    updateData,
  };
}