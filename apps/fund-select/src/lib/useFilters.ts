/**
 * 筛选状态 + URL 双向同步
 *
 * 状态-URL 对照：
 *   - 裸路径（无任何 numeric 参数）→ 默认值 DEFAULT_FILTERS（首屏体验）
 *   - 任意 numeric 参数出现 → URL 中的字段用 URL 值，缺失字段 = null（不限）
 *   - cleared=1 → 全部不限（用户主动"清空"）
 *
 * useFilters(initial) 接受 override：股票 tab 传 STOCK_DEFAULT_FILTERS；
 * 债基 tab 不传，走 DEFAULT_FILTERS。
 *
 * 例：
 *   /                                    → 默认 (3, 5, 5, 5)
 *   ?min_age=5&min_size_yi=5&...         → 显式覆盖，缺失 = null
 *   ?cleared=1                           → 全部 null
 */
'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { DEFAULT_FILTERS, type FundFilters } from './types';

type FilterKey = 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp' | 'sort' | 'order';

const NUMERIC_KEYS: FilterKey[] = ['min_age', 'min_size_yi', 'max_dd_3y', 'min_mgr_exp'];

/** 从 URL 解析筛选 */
export function parseFiltersFromSearch(
  search: URLSearchParams,
  fallback: FundFilters = DEFAULT_FILTERS,
): FundFilters {
  if (search.get('cleared') === '1') {
    // 用户主动"清空"：全部不限
    return {
      min_age: null,
      min_size_yi: null,
      max_dd_3y: null,
      min_mgr_exp: null,
      sort: (search.get('sort') as string) || fallback.sort,
      order: (search.get('order') as 'asc' | 'desc') || fallback.order,
    };
  }

  const hasNumeric = NUMERIC_KEYS.some(k => search.has(k));
  if (!hasNumeric) {
    // 首次访问或没改过筛选：套用默认（可能为 STOCK_DEFAULT_FILTERS）
    return { ...fallback };
  }

  // URL 有部分 numeric：缺失字段 = null（不允许 fallback 到默认值）
  const filters: FundFilters = {
    min_age: null,
    min_size_yi: null,
    max_dd_3y: null,
    min_mgr_exp: null,
    sort: fallback.sort,
    order: fallback.order,
  };
  for (const key of NUMERIC_KEYS) {
    const raw = search.get(key);
    if (raw === null || raw === '') continue;
    const v = Number(raw);
    if (Number.isFinite(v) && v >= 0) {
      (filters[key] as number | null) = v;
    }
  }
  const sort = search.get('sort');
  if (sort) filters.sort = sort;
  const order = search.get('order');
  if (order === 'asc' || order === 'desc') filters.order = order;
  return filters;
}

/** 筛选 → URL 查询串 */
export function filtersToSearch(filters: FundFilters): URLSearchParams {
  const params = new URLSearchParams();
  const allNull = NUMERIC_KEYS.every(k => filters[k] === null);
  if (allNull) {
    // 全部不限 → 用 cleared=1 区分于"首次访问默认"
    params.set('cleared', '1');
  } else {
    // 仅写非 null 字段；缺失字段由 URL 语义识别为 null（不限）
    for (const key of NUMERIC_KEYS) {
      const v = filters[key] as number | null;
      if (v !== null && v !== undefined) params.set(key, String(v));
    }
  }
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort);
  if (filters.order !== DEFAULT_FILTERS.order) params.set('order', filters.order);
  return params;
}

/** 只推 ?query，不要拼 location.pathname（含 basePath，router.push 会再叠一层） */
function pushQuery(
  router: { push: (href: string, opts?: { scroll?: boolean }) => void },
  params: URLSearchParams,
) {
  const qs = params.toString();
  router.push(qs ? `?${qs}` : '?', { scroll: false });
}

export function useFilters(initial?: Partial<FundFilters>) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const merged = useMemo<FundFilters>(
    () => ({ ...DEFAULT_FILTERS, ...(initial ?? {}) } as FundFilters),
    [initial],
  );

  const filters = useMemo(
    () => parseFiltersFromSearch(searchParams, merged),
    [searchParams, merged],
  );

  /** 更新一个维度并同步 URL（push，可回退） */
  const setFilter = useCallback((key: FilterKey, value: number | string | null) => {
    const next: FundFilters = { ...filters };
    if (key === 'sort') {
      next.sort = value as string;
    } else if (key === 'order') {
      next.order = (value === 'asc' ? 'asc' : 'desc');
    } else {
      (next[key] as number | null) = value === null || value === '' ? null : Number(value);
    }
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 排序切换：同字段翻转方向，异字段重置为 desc */
  const toggleSort = useCallback((field: string) => {
    if (filters.sort === field) {
      setFilter('order', filters.order === 'desc' ? 'asc' : 'desc');
    } else {
      const next: FundFilters = { ...filters, sort: field, order: 'desc' };
      pushQuery(router, filtersToSearch(next));
    }
  }, [filters, setFilter, router]);

  /** 清空全部筛选（保留 sort/order） */
  const clearAll = useCallback(() => {
    const next: FundFilters = {
      ...filters,
      min_age: null,
      min_size_yi: null,
      max_dd_3y: null,
      min_mgr_exp: null,
    };
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 已激活的筛选维度数（chip 用） */
  const activeCount = NUMERIC_KEYS.filter(
    k => (filters[k] as number | null) !== null
  ).length;

  return { filters, setFilter, toggleSort, clearAll, activeCount };
}
