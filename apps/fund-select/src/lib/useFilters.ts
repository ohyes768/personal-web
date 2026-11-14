/**
 * 筛选状态 + URL 双向同步
 *
 * 状态-URL 对照：
 *   - 裸路径（无任何 numeric 参数）→ 默认值 DEFAULT_FILTERS（首屏体验）
 *   - 任意 numeric 参数出现 → URL 中的字段用 URL 值，缺失字段 = null（不限）
 *   - cleared=1 → 全部不限（用户主动"清空"）
 *   - exclude_qdii=1 与 numeric / cleared 正交：仅此参数仍套用默认四维
 *   - market_type=债券型,定开债券 → 缩窄到这些类型；空 = 走 tab 默认 universe
 *   - page=N（≠1）、limit=K（≠50）写入 URL；默认值省略（避免噪音）
 *   - search_code=002910 → 代码搜索态：列表锁定这一只（11-16）
 *     与筛选参数**并存**：进入/退出搜索都不动任何筛选维度
 *     与 `code=`（直达并自动开抽屉）正交，两个参数各管一件事
 *
 * useFilters(initial) 接受 override：股票 tab 传 STOCK_DEFAULT_FILTERS；
 * discovery tab 传 DISCOVERY_*_DEFAULT_FILTERS；债基 tab 不传，走 DEFAULT_FILTERS。
 *
 * 例：
 *   /                                    → 默认 (3, 5, 5, 5)
 *   ?min_age=5&min_size_yi=5&...         → 显式覆盖，缺失 = null
 *   ?cleared=1                           → 全部 null
 *   ?exclude_qdii=1                      → 默认四维 + 排除 QDII
 *   ?market_type=债券型                  → market_types=['债券型']
 *   ?page=2&limit=25                     → 第 2 页 / 每页 25
 *   ?search_code=002910                  → 代码搜索（默认四维照旧，只影响展示）
 */
'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { parseSearchCode, searchCodeToParam } from './search-code';
import { DEFAULT_FILTERS, LIMIT_OPTIONS, type FundFilters, type SourceSegment } from './types';

export type NumericFilterKey = 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp' | 'min_sharpe';
export type FilterKey = NumericFilterKey | 'sort' | 'order' | 'exclude_qdii' | 'market_types' | 'source';

const NUMERIC_KEYS: NumericFilterKey[] = ['min_age', 'min_size_yi', 'max_dd_3y', 'min_mgr_exp', 'min_sharpe'];
const DEFAULT_LIMIT = 50;

const SOURCE_VALUES = ['all', 'curated', 'market'] as const;

/** 解析 ?source=：命中合法值用之，否则回退到该 tab 的默认分段
 *  （债基默认 all、股基默认 market —— 由 DEFAULT_FILTERS / STOCK_DEFAULT_FILTERS 决定）。 */
function parseSource(search: URLSearchParams, fallback: SourceSegment = 'all'): SourceSegment {
  const raw = search.get('source');
  return SOURCE_VALUES.includes(raw as SourceSegment) ? (raw as SourceSegment) : fallback;
}

function parseExcludeQdii(search: URLSearchParams): boolean {
  return search.get('exclude_qdii') === '1';
}

function parseMarketTypes(search: URLSearchParams): string[] | null {
  const raw = search.get('market_type');
  if (raw == null) return null;
  const out = raw.split(',').map(s => s.trim()).filter(Boolean);
  return out.length > 0 ? out : null;
}

function parsePage(search: URLSearchParams): number {
  const raw = search.get('page');
  if (raw == null) return 1;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1;
}

function parseLimit(search: URLSearchParams): number {
  const raw = search.get('limit');
  if (raw == null) return DEFAULT_LIMIT;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_LIMIT;
  // 取最近的合法选项（25/50/100），避免 URL 写 99 等非白名单值
  const nearest = LIMIT_OPTIONS.reduce((best, opt) =>
    Math.abs(opt - n) < Math.abs(best - n) ? opt : best
  );
  return nearest;
}

/** 从 URL 解析筛选 */
export function parseFiltersFromSearch(
  search: URLSearchParams,
  fallback: FundFilters = DEFAULT_FILTERS,
): FundFilters {
  // 代码搜索态：与筛选参数并存（搜索不清筛选，退出搜索后原筛选原样回来）
  const search_code = parseSearchCode(search.get('search_code'));
  const exclude_qdii = parseExcludeQdii(search);
  const market_types = parseMarketTypes(search);
  const source = parseSource(search, fallback.source ?? 'all');
  const page = parsePage(search);
  const limit = parseLimit(search);
  if (search.get('cleared') === '1') {
    // 用户主动"清空"：全部维度不限；exclude_qdii / market_types / source 仍按 URL 正交解析
    return {
      min_age: null,
      min_size_yi: null,
      max_dd_3y: null,
      min_mgr_exp: null,
      min_sharpe: null,
      exclude_qdii,
      market_types,
      search_code,
      source,
      sort: (search.get('sort') as string) || fallback.sort,
      order: (search.get('order') as 'asc' | 'desc') || fallback.order,
      page,
      limit,
    };
  }

  const hasNumeric = NUMERIC_KEYS.some(k => search.has(k));
  if (!hasNumeric) {
    // 首次访问或没改过筛选：套用默认（可能为 STOCK_DEFAULT_FILTERS / DISCOVERY_*_DEFAULT_FILTERS）
    return {
      ...fallback,
      exclude_qdii,
      market_types: market_types ?? fallback.market_types,
      search_code,
      source,
      page,
      limit,
    };
  }

  // URL 有部分 numeric：缺失字段 = null（不允许 fallback 到默认值）
  const filters: FundFilters = {
    min_age: null,
    min_size_yi: null,
    max_dd_3y: null,
    min_mgr_exp: null,
    min_sharpe: null,
    exclude_qdii,
    market_types,
    search_code,
    source,
    sort: fallback.sort,
    order: fallback.order,
    page,
    limit,
  };
  for (const key of NUMERIC_KEYS) {
    const raw = search.get(key);
    if (raw === null || raw === '') continue;
    const v = Number(raw);
    if (Number.isFinite(v) && v >= 0) {
      filters[key] = v;
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
      const v = filters[key];
      if (v !== null && v !== undefined) params.set(key, String(v));
    }
  }
  if (filters.exclude_qdii) params.set('exclude_qdii', '1');
  if (filters.market_types && filters.market_types.length > 0) {
    params.set('market_type', filters.market_types.join(','));
  }
  // 来源分段（11-15-source-segmented）：all = 默认不写 URL（避免噪音）
  if (filters.source && filters.source !== 'all') params.set('source', filters.source);
  // 代码搜索态（11-16）：与筛选参数并存，仅在有效时写入
  const searchCode = searchCodeToParam(filters.search_code);
  if (searchCode) params.set('search_code', searchCode);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort);
  if (filters.order !== DEFAULT_FILTERS.order) params.set('order', filters.order);
  // 分页：默认 page=1 / limit=50 不写 URL；其余写
  if (filters.page > 1) params.set('page', String(filters.page));
  if (filters.limit !== DEFAULT_LIMIT) params.set('limit', String(filters.limit));
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

  /** 更新一个维度并同步 URL（push，可回退）。
   * numeric / exclude_qdii / market_types 改动时强制 page=1（命中集变了，原 page 没意义）。
   * sort / order 改动不影响 page（用户在排序字段之间翻页是合理操作）。
   *
   * 11-16：任何**筛选类**改动都退出代码搜索态（命中集语义变了，锁单只已无意义）。
   * 搜索态本身由 setSearchCode 单独管理，不走这里（否则会被这条规则清掉自己）。
   */
  const setFilter = useCallback((key: FilterKey, value: number | string | boolean | string[] | null) => {
    const next: FundFilters = { ...filters };
    const dropsSearch = key !== 'sort' && key !== 'order';
    if (dropsSearch) next.search_code = null;
    if (key === 'sort') {
      next.sort = value as string;
    } else if (key === 'order') {
      next.order = (value === 'asc' ? 'asc' : 'desc');
    } else if (key === 'exclude_qdii') {
      next.exclude_qdii = Boolean(value);
      next.page = 1;
    } else if (key === 'market_types') {
      next.market_types = Array.isArray(value) && value.length > 0 ? (value as string[]) : null;
      next.page = 1;
    } else if (key === 'source') {
      next.source = (value as SourceSegment);
      next.page = 1;
      // 换分段时清掉「基金类型」：该筛选只在「市场」态暴露，留着会在
      // 「三分法」态里静默收窄名单（UI 上又看不到这个条件）
      next.market_types = null;
    } else {
      next[key] = value === null || value === '' ? null : Number(value);
      next.page = 1;
    }
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /**
   * 进入/退出代码搜索态（11-16）。**不动任何筛选维度**：
   * 搜索只决定「列表显示哪些」，退出后原筛选原样回来。
   *
   * 进入时 page 重置为 1（结果只有 1 条）；退出时也置 1（搜索期间翻的页无意义）。
   */
  const setSearchCode = useCallback((code: string | null) => {
    const next: FundFilters = {
      ...filters,
      search_code: parseSearchCode(code),
      page: 1,
    };
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 翻页：保持当前 limit；只改 page */
  const setPage = useCallback((page: number) => {
    const next: FundFilters = { ...filters, page: Math.max(1, Math.floor(page)) };
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 改每页条数：强制 page=1（位置变了，原 page 失去意义），并退出代码搜索态 */
  const setLimit = useCallback((limit: number) => {
    const next: FundFilters = { ...filters, limit, page: 1, search_code: null };
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 排序切换：同字段翻转方向，异字段重置为 desc；保持 page 不变（不退出搜索态） */
  const toggleSort = useCallback((field: string) => {
    if (filters.sort === field) {
      setFilter('order', filters.order === 'desc' ? 'asc' : 'desc');
    } else {
      const next: FundFilters = { ...filters, sort: field, order: 'desc' };
      pushQuery(router, filtersToSearch(next));
    }
  }, [filters, setFilter, router]);

  /** 清空全部筛选（保留 sort/order，关掉排除 QDII，重置 market_types；page 重置为 1）
   *  同时退出代码搜索态：用户点「清空」就是要回到完整列表。 */
  const clearAll = useCallback(() => {
    const next: FundFilters = {
      ...filters,
      min_age: null,
      min_size_yi: null,
      max_dd_3y: null,
      min_mgr_exp: null,
      min_sharpe: null,
      exclude_qdii: false,
      market_types: null,
      search_code: null,
      page: 1,
    };
    pushQuery(router, filtersToSearch(next));
  }, [filters, router]);

  /** 已激活的筛选维度数（chip 用）。代码搜索态不算一个「筛选维度」：
   *  它有自己的 chip，混进筛选计数会让「筛选(3)」与实际维度对不上。 */
  const activeCount = NUMERIC_KEYS.filter(
    k => filters[k] !== null
  ).length
    + (filters.exclude_qdii ? 1 : 0)
    + (filters.market_types && filters.market_types.length > 0 ? 1 : 0);

  return { filters, setFilter, setSearchCode, toggleSort, clearAll, setPage, setLimit, activeCount };
}
