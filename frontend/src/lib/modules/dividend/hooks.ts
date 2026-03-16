/**
 * 股息率模块自定义 Hooks
 * 封装组件中可复用的状态逻辑
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { dividendApi } from './api';
import type {
  DividendStock,
  DividendQueryParams,
  TechnicalIndicators,
  DeviationCache,
  RefreshState,
  RealtimePriceRequest,
  StockInfo,
  DividendStockWithTechnical,
} from './types';

/**
 * 股息率数据 Hook
 */
export function useDividendData() {
  const [data, setData] = useState<DividendStock[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (params?: DividendQueryParams) => {
    setLoading(true);
    setError(null);
    try {
      const response = await dividendApi.getStocks(params);
      setData(response.items);
      setTotal(response.total);
    } catch (err) {
      const message = err instanceof Error ? err.message : '获取数据失败';
      setError(message);
      console.error('Failed to fetch dividend data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 默认参数：阈值 3%，降序排序
    fetchData({
      min_yield: 5,
      sort_by: 'avg_yield_3y',
      sort_order: 'desc',
    });
  }, [fetchData]);

  return { data, total, loading, error, refetch: fetchData };
}

/**
 * 技术指标数据 Hook
 * 获取 PE/PB 和 M120 数据
 */
export function useTechnicalData(stockCodes: string[]) {
  const [technicalData, setTechnicalData] = useState<Map<string, TechnicalIndicators>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 使用 useMemo 缓存 stockCodes，避免无限循环
  const memoizedStockCodes = useMemo(() => stockCodes, [JSON.stringify(stockCodes)]);

  useEffect(() => {
    if (memoizedStockCodes.length === 0) {
      setTechnicalData(new Map());
      return;
    }

    const fetchTechnicalData = async () => {
      setLoading(true);
      setError(null);

      try {
        // 并行获取 PE 和 M120 数据
        const codesStr = memoizedStockCodes.join(',');
        const [peResponse, m120Response] = await Promise.all([
          dividendApi.getPEData({ codes: codesStr }),
          dividendApi.getM120Data(),
        ]);

        const newTechnicalData = new Map<string, TechnicalIndicators>();

        // 处理 PE 数据
        const peMap = new Map(peResponse.items.map(item => [item.code, item]));

        // 处理 M120 数据
        const m120Map = new Map(m120Response.items.map(item => [item.code, item]));

        // 合并数据
        memoizedStockCodes.forEach(code => {
          const pe = peMap.get(code);
          const m120 = m120Map.get(code);

          if (pe || m120) {
            newTechnicalData.set(code, {
              pe: pe?.pe ?? null,
              pb: pe?.pb ?? null,
              m120: m120?.m120 ?? null,
              close: m120?.close ?? null,
              deviation: m120?.deviation ?? null,
            });
          }
        });

        setTechnicalData(newTechnicalData);
      } catch (err) {
        const message = err instanceof Error ? err.message : '获取技术指标数据失败';
        setError(message);
        console.error('Failed to fetch technical data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTechnicalData();
  }, [memoizedStockCodes]);

  return { technicalData, loading, error };
}

/**
 * 详情弹框状态 Hook
 */
export function useDetailModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [modalType, setModalType] = useState<'quarterly' | 'sector' | 'yearly' | 'volatility' | null>(null);
  const [stock, setStock] = useState<DividendStock | null>(null);

  const open = useCallback((type: 'quarterly' | 'sector' | 'yearly' | 'volatility', stockData: DividendStock) => {
    setModalType(type);
    setStock(stockData);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    // 延迟清空，等待动画完成
    setTimeout(() => {
      setModalType(null);
      setStock(null);
    }, 300);
  }, []);

  return { isOpen, modalType, stock, open, close };
}

/**
 * 实时股价刷新 Hook
 */
export function useRefreshPrice() {
  const [refreshStates, setRefreshStates] = useState<Map<string, RefreshState>>(new Map());

  // 缓存相关
  const CACHE_KEY_PREFIX = 'dividend-deviation-';
  const CACHE_DURATION = 24 * 60 * 60 * 1000; // 1天（毫秒）

  /**
   * 从 localStorage 读取缓存
   */
  const getCache = useCallback((code: string): DeviationCache | null => {
    try {
      const cached = localStorage.getItem(`${CACHE_KEY_PREFIX}${code}`);
      if (!cached) return null;

      const data: DeviationCache = JSON.parse(cached);
      const now = Date.now();

      // 检查缓存是否过期
      if (now - data.timestamp > CACHE_DURATION) {
        localStorage.removeItem(`${CACHE_KEY_PREFIX}${code}`);
        return null;
      }

      return data;
    } catch {
      return null;
    }
  }, []);

  /**
   * 保存到 localStorage
   */
  const setCache = useCallback((code: string, close: number, deviation: number) => {
    try {
      const data: DeviationCache = {
        close,
        deviation,
        timestamp: Date.now(),
      };
      localStorage.setItem(`${CACHE_KEY_PREFIX}${code}`, JSON.stringify(data));
    } catch (err) {
      console.error('Failed to save cache:', err);
    }
  }, []);

  /**
   * 刷新实时股价
   */
  const refresh = useCallback(async (request: RealtimePriceRequest): Promise<{ close: number; deviation: number } | null> => {
    const { code } = request;

    // 设置加载状态
    setRefreshStates(prev => {
      const newStates = new Map(prev);
      newStates.set(code, { loading: true, error: null });
      return newStates;
    });

    try {
      // 检查缓存
      const cached = getCache(code);
      if (cached) {
        setRefreshStates(prev => {
          const newStates = new Map(prev);
          newStates.set(code, { loading: false, error: null });
          return newStates;
        });
        return { close: cached.close, deviation: cached.deviation };
      }

      // 调用 API 获取实时股价
      const response = await dividendApi.getRealtimePrice(request);

      if (response.close && response.deviation != null) {
        // 保存到缓存
        setCache(code, response.close, response.deviation);

        // 更新状态
        setRefreshStates(prev => {
          const newStates = new Map(prev);
          newStates.set(code, { loading: false, error: null });
          return newStates;
        });

        return { close: response.close, deviation: response.deviation };
      }

      return null;
    } catch (err) {
      const message = err instanceof Error ? err.message : '刷新失败';
      setRefreshStates(prev => {
        const newStates = new Map(prev);
        newStates.set(code, { loading: false, error: message });
        return newStates;
      });
      console.error('Failed to refresh price:', err);
      return null;
    }
  }, [getCache, setCache]);

  /**
   * 获取指定股票的刷新状态
   */
  const getRefreshState = useCallback((code: string): RefreshState => {
    return refreshStates.get(code) || { loading: false, error: null };
  }, [refreshStates]);

  return { refresh, getRefreshState, getCache };
}

/**
 * 股票基础信息 Hook
 * 批量获取股票的交易所和申万行业信息（用于列表显示）
 */
export function useStockInfo(stockCodes: string[]) {
  const [stockInfoMap, setStockInfoMap] = useState<Map<string, StockInfo>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 使用 useMemo 缓存 stockCodes，避免无限循环
  const memoizedStockCodes = useMemo(() => stockCodes, [JSON.stringify(stockCodes)]);

  useEffect(() => {
    if (memoizedStockCodes.length === 0) {
      setStockInfoMap(new Map());
      return;
    }

    const fetchStockInfo = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await dividendApi.getStocksInfo({ codes: memoizedStockCodes });

        const infoMap = new Map<string, StockInfo>();
        response.items.forEach(item => {
          infoMap.set(item.code, item);
        });

        setStockInfoMap(infoMap);
      } catch (err) {
        const message = err instanceof Error ? err.message : '获取股票信息失败';
        setError(message);
        console.error('Failed to fetch stock info:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStockInfo();
  }, [memoizedStockCodes]);

  return { stockInfoMap, loading, error };
}

/**
 * 股票对比功能 Hook
 */
export function useCompare(maxSelect: number = 5) {
  const [selectedStocks, setSelectedStocks] = useState<DividendStock[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  /**
   * 切换选中状态
   */
  const toggleStock = useCallback((stock: DividendStock) => {
    setSelectedStocks(prev => {
      const exists = prev.some(s => s.code === stock.code);
      if (exists) {
        return prev.filter(s => s.code !== stock.code);
      }
      if (prev.length >= maxSelect) {
        return prev;
      }
      return [...prev, stock];
    });
  }, [maxSelect]);

  /**
   * 清空选中
   */
  const clearSelection = useCallback(() => {
    setSelectedStocks([]);
    setIsDrawerOpen(false);
  }, []);

  /**
   * 打开对比抽屉
   */
  const openDrawer = useCallback(() => {
    if (selectedStocks.length < 2) {
      return false;
    }
    setIsDrawerOpen(true);
    return true;
  }, [selectedStocks.length]);

  /**
   * 关闭对比抽屉
   */
  const closeDrawer = useCallback(() => {
    setIsDrawerOpen(false);
  }, []);

  /**
   * 移除股票
   */
  const removeStock = useCallback((code: string) => {
    setSelectedStocks(prev => prev.filter(s => s.code !== code));
  }, []);

  /**
   * 检查是否已选中
   */
  const isSelected = useCallback((code: string) => {
    return selectedStocks.some(s => s.code === code);
  }, [selectedStocks]);

  return {
    selectedStocks,
    isDrawerOpen,
    toggleStock,
    clearSelection,
    openDrawer,
    closeDrawer,
    removeStock,
    isSelected,
  };
}

/**
 * 高亮信息计算 Hook
 */
export function useHighlights(stocks: DividendStock[]) {
  return useMemo(() => {
    const yieldIndex = stocks.findIndex(s => s.avg_yield_3y === Math.max(...stocks.map(s => s.avg_yield_3y ?? -Infinity)));
    const peValues = stocks.map(s => {
      const pe = (s as DividendStockWithTechnical).technical?.pe;
      return pe ?? Infinity;
    });
    const peIndex = peValues.indexOf(Math.min(...peValues));
    const pbValues = stocks.map(s => {
      const pb = (s as DividendStockWithTechnical).technical?.pb;
      return pb ?? Infinity;
    });
    const pbIndex = pbValues.indexOf(Math.min(...pbValues));
    // 昨日收盘/M120 比率，最小值为最优
    const ratioValues = stocks.map(s => {
      const technical = (s as DividendStockWithTechnical).technical;
      if (technical?.close && technical?.m120) {
        return technical.close / technical.m120;
      }
      return Infinity;
    });
    const ratioIndex = ratioValues.indexOf(Math.min(...ratioValues));
    // 最高涨幅，最大值为最优
    const highChangeValues = stocks.map(s => s.high_change_pct_2025 ?? -Infinity);
    const highChangeIndex = highChangeValues.indexOf(Math.max(...highChangeValues));
    // 最高跌幅，绝对值最小为最优
    const lowChangeValues = stocks.map(s => {
      const lowChange = s.low_change_pct_2025;
      if (lowChange === null || lowChange === undefined) return Infinity;
      return Math.abs(lowChange);
    });
    const lowChangeIndex = lowChangeValues.indexOf(Math.min(...lowChangeValues));

    return {
      yieldIndex: yieldIndex >= 0 ? yieldIndex : null,
      peIndex: peIndex >= 0 ? peIndex : null,
      pbIndex: pbIndex >= 0 ? pbIndex : null,
      ratioIndex: ratioIndex >= 0 ? ratioIndex : null,
      highChangeIndex: highChangeIndex >= 0 ? highChangeIndex : null,
      lowChangeIndex: lowChangeIndex >= 0 ? lowChangeIndex : null,
    };
  }, [stocks]);
}