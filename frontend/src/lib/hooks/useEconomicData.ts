/**
 * 经济数据获取 Hook - 全量数据加载策略
 */
import { useState, useEffect } from 'react';
import type { TimeRange, EconomicDataResponse, TabType } from '../types/economic';
import { economicApi } from '../api/economic';
import { calculateDateRange } from '../utils/dateCalculators';
import { filterDataByTab, filterMonthlyData } from '../utils/dataFilterUtils';

interface UseEconomicDataResult {
  data: EconomicDataResponse | null;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

// 全量数据缓存 Key
const FULL_DATA_CACHE_KEY = 'economic_data_full_cache';

// 默认的经济数据结构
function getDefaultEconomicData(): EconomicDataResponse {
  return {
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
  };
}

export function useEconomicData(timeRange: TimeRange, tabType: TabType = 'treasury-exchange'): UseEconomicDataResult {
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [filteredData, setFilteredData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCached, setIsCached] = useState(false);

  // 根据时间和Tab类型过滤数据
  const filterDataByTimeAndTab = (
    data: EconomicDataResponse,
    range: TimeRange,
    tab: TabType
  ): EconomicDataResponse => {
    // 如果是德债日债Tab，先过滤月度数据
    let processedData = data;
    if (tab === 'bonds') {
      processedData = filterMonthlyData(data);
    }

    const { startDate, endDate } = calculateDateRange(range);

    // 如果是全部数据，直接返回
    if (range === 'ALL') {
      const result = filterDataByTab(processedData!, tab, range);
      return result || getDefaultEconomicData();
    }

    // 找到起始和结束索引
    const dates = processedData!.dates;
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

    // 先按时间范围过滤，再按Tab类型过滤
    const timeFiltered = {
      dates: filteredDates,
      us_treasuries: {
        '3m': processedData!.us_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData!.us_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData!.us_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      eu_treasuries: {
        '3m': processedData!.eu_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData!.eu_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData!.eu_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      jp_treasuries: {
        '3m': processedData!.jp_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData!.jp_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData!.jp_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      exchange_rates: processedData!.exchange_rates ? {
        dollar_index: processedData!.exchange_rates.dollar_index?.slice(startIndex, endIndex) ?? [],
        usd_cny: processedData!.exchange_rates.usd_cny?.slice(startIndex, endIndex) ?? [],
        usd_jpy: processedData!.exchange_rates.usd_jpy?.slice(startIndex, endIndex) ?? [],
        usd_eur: processedData!.exchange_rates.usd_eur?.slice(startIndex, endIndex) ?? [],
      } : undefined,
      vix: processedData!.vix?.slice(startIndex, endIndex) ?? [],
    };

    const result = filterDataByTab(timeFiltered, tab, range);
    return result || getDefaultEconomicData();
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
          const isOldFormat = !parsed.data?.eu_treasuries;
          if (Date.now() - parsed.timestamp < 3600000 && !isOldFormat) {
            setFullData(parsed.data);
            setIsCached(true);
            setIsLoading(false);
            return;
          }
          // 如果是旧格式，清除缓存
          if (isOldFormat) {
            localStorage.removeItem(FULL_DATA_CACHE_KEY);
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

  // 根据时间范围和Tab类型过滤数据
  useEffect(() => {
    if (fullData) {
      setFilteredData(filterDataByTimeAndTab(fullData, timeRange, tabType));
    }
  }, [fullData, timeRange, tabType]);

  return {
    data: filteredData,
    fullData,
    isLoading,
    error,
    isCached,
  };
}
