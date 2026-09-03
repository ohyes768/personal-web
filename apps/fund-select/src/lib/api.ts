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
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.order) params.set('order', filters.order);
  if (filters.exclude_qdii) params.set('exclude_qdii', 'true');
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
