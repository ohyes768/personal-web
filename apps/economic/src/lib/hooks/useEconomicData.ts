/**
 * 经济数据获取 Hook - 全量数据加载策略
 */
import { useState, useEffect } from 'react';
import type { TimeRange, EconomicDataResponse, TabType } from '../types/economic';
import { economicApi } from '../modules/economic/api';
import { calculateDateRange, TIME_RANGE_MAP } from '../utils/dateCalculators';
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
    commodities: {
      gold: [],
      silver: [],
      oil: [],
      copper: [],
    },
    indices: {
      HKHSI: [],
      SH000001: [],
      SPX: [],
      IXIC: [],
      DJI: [],
    },
  };
}

export function useEconomicData(
  timeRange: TimeRange,
  tabType: TabType = 'treasury-exchange',
  refreshKey: number = 0
): UseEconomicDataResult {
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

    // 用数据最后一天作为 endDate 基准（如果数据比 today 旧，caller 传的 endDate 会让 findIndex 全失败）
    // 这样 startDate 倒推也有意义
    const dataLastDate = dates[dates.length - 1];
    const effectiveEndDate = dataLastDate && (!endDate || dataLastDate < endDate) ? dataLastDate : endDate;

    if (startDate && effectiveEndDate) {
      // 从 effectiveEndDate 倒推 days 天作为新的 startDate
      const days = TIME_RANGE_MAP[range];
      if (days && Number.isFinite(days)) {
        const t = new Date(effectiveEndDate);
        t.setDate(t.getDate() - days);
        const adjustedStart = t.toISOString().split('T')[0];
        startIndex = dates.findIndex(d => d >= adjustedStart);
        if (startIndex === -1) {
          // 兜底：从末尾往回数（按交易日密度 0.7 估算）
          startIndex = Math.max(0, dates.length - Math.floor(days * 0.7));
        }
      } else {
        startIndex = dates.findIndex(d => d >= startDate);
        if (startIndex === -1) startIndex = 0;
      }
    }

    if (effectiveEndDate) {
      endIndex = dates.findIndex(d => d > effectiveEndDate);
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
      // 以下字段对比模块需要，必须保留
      fund_flow: processedData!.fund_flow ? {
        north_net_flow: processedData!.fund_flow.north_net_flow?.slice(startIndex, endIndex) ?? [],
        north_buy: processedData!.fund_flow.north_buy?.slice(startIndex, endIndex) ?? [],
        north_sell: processedData!.fund_flow.north_sell?.slice(startIndex, endIndex) ?? [],
        south_net_flow: processedData!.fund_flow.south_net_flow?.slice(startIndex, endIndex) ?? [],
        south_buy: processedData!.fund_flow.south_buy?.slice(startIndex, endIndex) ?? [],
        south_sell: processedData!.fund_flow.south_sell?.slice(startIndex, endIndex) ?? [],
      } : undefined,
      china_bond: processedData!.china_bond ? {
        '10y': processedData!.china_bond['10y']?.slice(startIndex, endIndex) ?? [],
      } : undefined,
      ted_spread: processedData!.ted_spread ? {
        sofr: processedData!.ted_spread.sofr?.slice(startIndex, endIndex) ?? [],
        us_3m: processedData!.ted_spread.us_3m?.slice(startIndex, endIndex) ?? [],
        ted_spread: processedData!.ted_spread.ted_spread?.slice(startIndex, endIndex) ?? [],
      } : undefined,
      commodities: processedData!.commodities ? {
        gold: processedData!.commodities.gold?.slice(startIndex, endIndex) ?? [],
        silver: processedData!.commodities.silver?.slice(startIndex, endIndex) ?? [],
        oil: processedData!.commodities.oil?.slice(startIndex, endIndex) ?? [],
        copper: processedData!.commodities.copper?.slice(startIndex, endIndex) ?? [],
      } : undefined,
      indices: processedData!.indices ? {
        HKHSI: processedData!.indices.HKHSI?.slice(startIndex, endIndex) ?? [],
        SH000001: processedData!.indices.SH000001?.slice(startIndex, endIndex) ?? [],
        SPX: processedData!.indices.SPX?.slice(startIndex, endIndex) ?? [],
        IXIC: processedData!.indices.IXIC?.slice(startIndex, endIndex) ?? [],
        DJI: processedData!.indices.DJI?.slice(startIndex, endIndex) ?? [],
      } : undefined,
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
        // 尝试从缓存读取全量数据（refreshKey > 0 表示手动刷新，跳过 cache）
        if (refreshKey === 0) {
          const cached = localStorage.getItem(FULL_DATA_CACHE_KEY);
          if (cached) {
            const parsed = JSON.parse(cached);
            const isOldFormat = !parsed.data?.eu_treasuries;
            if (Date.now() - parsed.timestamp < 3600000 && !isOldFormat) {
              setFullData(parsed.data);
              setIsCached(true);
              setIsLoading(false);
              return;
            }
            if (isOldFormat) {
              localStorage.removeItem(FULL_DATA_CACHE_KEY);
            }
          }
        } else {
          // 手动刷新：清掉旧 cache
          localStorage.removeItem(FULL_DATA_CACHE_KEY);
        }

        // 从API获取全量数据
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
  }, [refreshKey]); // refreshKey 变化时强制重新 fetch（跳过 cache）

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
