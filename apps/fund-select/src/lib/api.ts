/**
 * 后端 API client（走 Next.js catch-all 代理，同源）
 */
import type {
  FundDetail,
  RefreshStatus,
  ScreenResponse,
  StatsResponse,
} from './types';
import type { FundFilters } from './types';

const BASE = '/funds/api/funds';  // 原生 fetch 不吃 basePath，需带全路径

function buildQuery(filters: Partial<FundFilters>): string {
  const params = new URLSearchParams();
  if (filters.min_age != null) params.set('min_age', String(filters.min_age));
  if (filters.min_size_yi != null) params.set('min_size_yi', String(filters.min_size_yi));
  if (filters.max_dd_3y != null) params.set('max_dd_3y', String(filters.max_dd_3y));
  if (filters.min_mgr_exp != null) params.set('min_mgr_exp', String(filters.min_mgr_exp));
  if (filters.min_sharpe != null) params.set('min_sharpe', String(filters.min_sharpe));
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.order) params.set('order', filters.order);
  if (filters.exclude_qdii) params.set('exclude_qdii', 'true');
  if (filters.market_types && filters.market_types.length > 0) {
    params.set('market_type', filters.market_types.join(','));
  }
  const q = params.toString();
  return q ? `?${q}` : '';
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`请求失败 ${res.status}: ${detail.slice(0, 120)}`);
  }
  return res.json() as Promise<T>;
}

export const fundApi = {
  screen(filters: Partial<FundFilters>, signal?: AbortSignal): Promise<ScreenResponse> {
    return getJson(`${BASE}/screen${buildQuery(filters)}`);
  },

  getDetail(code: string): Promise<FundDetail> {
    return getJson(`${BASE}/${code}`);
  },

  getStats(): Promise<StatsResponse> {
    return getJson(`${BASE}/stats`);
  },

  refresh(limit?: number): Promise<{ task_id: string; status: string }> {
    return getJson(`${BASE}/refresh${limit ? `?limit=${limit}` : ''}`);
  },

  getRefreshStatus(taskId?: string): Promise<RefreshStatus> {
    return getJson(`${BASE}/refresh/status${taskId ? `?task_id=${taskId}` : ''}`);
  },
};

/**
 * 股票基金 tab API（接口前缀 /api/funds/stock/*）
 * 与 fundApi 对偶：screen / getDetail / refresh / getRefreshStatus
 */
const STOCK_BASE = '/funds/api/funds/stock';

export const stockApi = {
  screen(filters: Partial<FundFilters>, signal?: AbortSignal): Promise<ScreenResponse> {
    return getJson(`${STOCK_BASE}/screen${buildQuery(filters)}`);
  },

  getDetail(code: string): Promise<FundDetail> {
    return getJson(`${STOCK_BASE}/${code}`);
  },

  refresh(limit?: number): Promise<{ task_id: string; status: string }> {
    return getJson(`${STOCK_BASE}/refresh${limit ? `?limit=${limit}` : ''}`);
  },

  getRefreshStatus(taskId?: string): Promise<RefreshStatus> {
    return getJson(`${STOCK_BASE}/refresh/status${taskId ? `?task_id=${taskId}` : ''}`);
  },
};

/**
 * 市场 tab API（接口前缀 /api/funds/discovery-{bond,stock}/*）
 * 单只详情复用 fundApi.getDetail（设计决策 D2：detail 不依赖 universe）
 */
const DISCOVERY_BOND_BASE = '/funds/api/funds/discovery-bond';
const DISCOVERY_STOCK_BASE = '/funds/api/funds/discovery-stock';

export const discoveryBondApi = {
  screen(filters: Partial<FundFilters>, signal?: AbortSignal): Promise<ScreenResponse> {
    return getJson(`${DISCOVERY_BOND_BASE}/screen${buildQuery(filters)}`);
  },

  getStats(): Promise<StatsResponse> {
    return getJson(`${DISCOVERY_BOND_BASE}/stats`);
  },

  refresh(): Promise<{ task_id: string; status: string }> {
    return getJson(`${DISCOVERY_BOND_BASE}/refresh`);
  },

  getRefreshStatus(taskId?: string): Promise<RefreshStatus> {
    return getJson(`${DISCOVERY_BOND_BASE}/refresh/status${taskId ? `?task_id=${taskId}` : ''}`);
  },
};

export const discoveryStockApi = {
  screen(filters: Partial<FundFilters>, signal?: AbortSignal): Promise<ScreenResponse> {
    return getJson(`${DISCOVERY_STOCK_BASE}/screen${buildQuery(filters)}`);
  },

  getStats(): Promise<StatsResponse> {
    return getJson(`${DISCOVERY_STOCK_BASE}/stats`);
  },

  refresh(): Promise<{ task_id: string; status: string }> {
    return getJson(`${DISCOVERY_STOCK_BASE}/refresh`);
  },

  getRefreshStatus(taskId?: string): Promise<RefreshStatus> {
    return getJson(`${DISCOVERY_STOCK_BASE}/refresh/status${taskId ? `?task_id=${taskId}` : ''}`);
  },
};
