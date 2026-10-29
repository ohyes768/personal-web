export type RunStatus = 'queued' | 'running' | 'success' | 'partial' | 'failed';
export interface CollectionResult {
  completed?: number;
  failed?: number;
  total?: number;
  errors?: string[];
  stage_results?: Record<string, { status: string; error?: string; result?: CollectionResult }>;
}
export interface RunItem {
  tab: string;
  start: string;
  end?: string;
  status: RunStatus;
  error?: string;
  result?: CollectionResult;
}
export interface SchedulerRun {
  run_id?: string;
  trigger?: 'scheduled' | 'manual';
  start: string;
  end?: string;
  status: RunStatus;
  error?: string;
  items: RunItem[];
}
export interface SchedulerJob {
  id: string;
  name: string;
  tab: string;
  description: string;
  enabled: boolean;
  running: boolean;
  cron_human: string;
  next_run_time: string | null;
  last_run: SchedulerRun | null;
  current_run: SchedulerRun | null;
}

const BASE = '/funds/api/funds/scheduler';
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, cache: 'no-store' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `请求失败（${response.status}），请重试`);
  }
  return response.json() as Promise<T>;
}
export const schedulerApi = {
  jobs: (signal?: AbortSignal) => request<{ jobs: SchedulerJob[] }>('/jobs', { signal }),
  runs: (id: string, signal?: AbortSignal) => request<{ runs: SchedulerRun[] }>(`/jobs/${encodeURIComponent(id)}/runs?limit=20`, { signal }),
  setEnabled: (id: string, enabled: boolean) => request<SchedulerJob>(`/jobs/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
  }),
  run: (id: string) => request<{ status: string }>(`/jobs/${encodeURIComponent(id)}/run`, { method: 'POST' }),
};
