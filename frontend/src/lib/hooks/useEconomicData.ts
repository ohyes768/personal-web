/**
 * 经济数据获取 Hook - 全量数据加载策略
 */
import { useState, useEffect } from 'react';
import type { TimeRange, EconomicDataResponse } from '../types/economic';
import { economicApi } from '../api/economic';
import { calculateDateRange } from '../utils/dateCalculators';

interface UseEconomicDataResult {
  data: EconomicDataResponse | null;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

// 全量数据缓存 Key
const FULL_DATA_CACHE_KEY = 'economic_data_full_cache';

export function useEconomicData(timeRange: TimeRange): UseEconomicDataResult {
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [filteredData, setFilteredData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCached, setIsCached] = useState(false);

  // 根据时间范围过滤数据
  const filterDataByTimeRange = (
    data: EconomicDataResponse,
    range: TimeRange
  ): EconomicDataResponse => {
    const { startDate, endDate } = calculateDateRange(range);

    // 如果是全部数据，直接返回
    if (range === 'ALL') {
      return data;
    }

    // 找到起始和结束索引
    const dates = data.dates;
    let startIndex = 0;
    let endIndex = dates.length;

    if (startDate) {
      startIndex = dates.findIndex(d => d >= startDate);
      if (startIndex === -1) startIndex = 0;
    }

    if (endDate) {
      endIndex = dates.findIndex(d => d > endDate);
      if (endIndex === -1) endIndex = dates.length;
    }

    // 过滤数据
    const filteredDates = dates.slice(startIndex, endIndex);

    return {
      dates: filteredDates,
      us_treasuries: {
        '3m': data.us_treasuries['3m'].slice(startIndex, endIndex),
        '2y': data.us_treasuries['2y'].slice(startIndex, endIndex),
        '10y': data.us_treasuries['10y'].slice(startIndex, endIndex),
      },
      exchange_rates: data.exchange_rates ? {
        dollar_index: data.exchange_rates.dollar_index.slice(startIndex, endIndex),
        usd_cny: data.exchange_rates.usd_cny.slice(startIndex, endIndex),
        usd_jpy: data.exchange_rates.usd_jpy.slice(startIndex, endIndex),
        usd_eur: data.exchange_rates.usd_eur.slice(startIndex, endIndex),
      } : undefined,
    };
  };

  // 首次加载全量数据
  useEffect(() => {
    const fetchFullData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // 尝试从缓存读取全量数据
        const cached = localStorage.getItem(FULL_DATA_CACHE_KEY);
        if (cached) {
          const parsed = JSON.parse(cached);
          // 检查缓存是否过期（1小时）
          if (Date.now() - parsed.timestamp < 3600000) {
            setFullData(parsed.data);
            setIsCached(true);
            setIsLoading(false);
            return;
          }
        }

        // 从API获取全量数据（传入很早的起始日期获取所有历史数据）
        // 后端从2000年开始有数据，传入2000-01-01获取全量
        const response = await economicApi.getData('2000-01-01', undefined);
        setFullData(response);
        setIsCached(false);

        // 写入缓存
        localStorage.setItem(FULL_DATA_CACHE_KEY, JSON.stringify({
          data: response,
          timestamp: Date.now(),
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : '获取数据失败';
        setError(message);
        console.error('获取经济数据失败:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchFullData();
  }, []); // 只在组件挂载时执行一次

  // 根据时间范围过滤数据
  useEffect(() => {
    if (fullData) {
      setFilteredData(filterDataByTimeRange(fullData, timeRange));
    }
  }, [fullData, timeRange]);

  return {
    data: filteredData,
    fullData,
    isLoading,
    error,
    isCached,
  };
}
