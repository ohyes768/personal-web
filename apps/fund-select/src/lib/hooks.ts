/**
 * 数据 hooks：useFundList / useCompare（泛型，从 dividend 移植泛型化）/ useFeeDetails
 */
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { fundApi, stockApi } from './api';
import type { FundDetail, FundFilters, FundListItem } from './types';

/**
 * 基金列表（筛选变化自动重拉）
 */
export function useFundList(filters: FundFilters) {
  const [items, setItems] = useState<FundListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const query = [
    filters.min_age, filters.min_size_yi, filters.max_dd_3y, filters.min_mgr_exp,
    filters.min_sharpe,
    filters.exclude_qdii, filters.sort, filters.order,
  ].join('|');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fundApi.screen(filters, controller.signal)
      .then(r => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch(err => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : '加载失败');
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, reloadNonce]);

  const reload = useCallback(() => setReloadNonce(n => n + 1), []);

  return { items, total, loading, error, reload };
}

/**
 * 股票基金列表（与 useFundList 同骨架，调 stockApi.screen）
 */
export function useStockFundList(filters: FundFilters) {
  const [items, setItems] = useState<FundListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const query = [
    filters.min_age, filters.min_size_yi, filters.max_dd_3y, filters.min_mgr_exp,
    filters.min_sharpe,
    filters.exclude_qdii, filters.sort, filters.order,
  ].join('|');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    stockApi.screen(filters, controller.signal)
      .then(r => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch(err => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : '加载失败');
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, reloadNonce]);

  const reload = useCallback(() => setReloadNonce(n => n + 1), []);

  return { items, total, loading, error, reload };
}

/** useCompare 的最小约束 */
export interface Comparable {
  code: string;
  name: string;
}

/**
 * 对比选择 Hook（从 dividend useCompare 泛型化）
 */
export function useCompare<T extends Comparable>(maxSelect: number = 5) {
  const [selected, setSelected] = useState<T[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const toggle = useCallback((item: T) => {
    setSelected(prev => {
      const exists = prev.some(s => s.code === item.code);
      if (exists) return prev.filter(s => s.code !== item.code);
      if (prev.length >= maxSelect) return prev;
      return [...prev, item];
    });
  }, [maxSelect]);

  const clearSelection = useCallback(() => {
    setSelected([]);
    setIsDrawerOpen(false);
  }, []);

  const openDrawer = useCallback(() => {
    if (selected.length < 2) return false;
    setIsDrawerOpen(true);
    return true;
  }, [selected.length]);

  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);

  const removeItem = useCallback((code: string) => {
    setSelected(prev => prev.filter(s => s.code !== code));
  }, []);

  const isSelected = useCallback(
    (code: string) => selected.some(s => s.code === code),
    [selected]
  );

  const isFull = selected.length >= maxSelect;

  return {
    selected,
    isDrawerOpen,
    isFull,
    toggle,
    clearSelection,
    openDrawer,
    closeDrawer,
    removeItem,
    isSelected,
  };
}

/**
 * 抽屉打开时按需拉所选基金的费率详情（申购/赎回档），合并进列表项
 */
export function useFeeDetails(selected: FundListItem[], enabled: boolean): FundListItem[] {
  const [detailMap, setDetailMap] = useState<Record<string, FundDetail>>({});

  const codes = useMemo(() => selected.map(s => s.code).join(','), [selected]);

  useEffect(() => {
    if (!enabled || !codes) return;
    let cancelled = false;
    Promise.all(
      codes.split(',').map(c => fundApi.getDetail(c).catch(() => null))
    ).then(details => {
      if (cancelled) return;
      const map: Record<string, FundDetail> = {};
      for (const d of details) {
        if (d) map[d.code] = d;
      }
      setDetailMap(map);
    });
    return () => {
      cancelled = true;
    };
  }, [codes, enabled]);

  return useMemo(
    () => selected.map(s => {
      const d = detailMap[s.code];
      return d ? { ...s, fees: d.fees } : s;
    }),
    [selected, detailMap]
  );
}
