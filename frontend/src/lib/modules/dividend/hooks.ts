/**
 * 股息率模块自定义 Hooks
 * 封装组件中可复用的状态逻辑
 */
import { useState, useEffect, useCallback } from 'react';
import { dividendApi } from './api';
import type { DividendStock, DividendQueryParams } from './types';

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
      min_yield: 3,
      sort_by: 'avg_yield_3y',
      sort_order: 'desc',
    });
  }, [fetchData]);

  return { data, total, loading, error, refetch: fetchData };
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