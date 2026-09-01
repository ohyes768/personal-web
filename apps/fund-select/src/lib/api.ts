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

  /** CSV 下载（blob → 触发浏览器下载，文件名取后端 content-disposition） */
  async exportCsv(filters: Partial<FundFilters>): Promise<void> {
    const res = await fetch(`${BASE}/export/csv${buildQuery(filters)}`);
    if (!res.ok) throw new Error(`导出失败 ${res.status}`);
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const m = disposition.match(/filename="?([^";]+)"?/);
    const filename = m ? m[1] : `funds_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.csv`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
