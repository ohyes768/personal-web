// 后端契约（docs/daily-review-design.md，路径已与后端 teammate 定死）
// 所有请求走 basePath 下的 rewrite：/review/api/* → ${DAILY_REVIEW_API_ORIGIN}/api/review/*

export interface ActivityItem {
  machine: string; // "windows" | "nas"
  kind: string; // session | commit | task ...
  project: string;
  title: string;
  summary_text: string;
  started_at: string;
  ended_at: string;
}

export interface DailyCount {
  day: string;
  count: number;
}

export interface ProjectSummary {
  project: string;
  last_activity: string;
  session_count: number;
  commit_count: number;
  task_board_count: number;
  active_days: number;
  total_count: number;
  daily_counts: DailyCount[];
  recent_summaries: { title: string; summary_text: string; started_at: string; kind: string; machine: string }[];
}

export type ReportType = "daily";

export interface ReportMeta {
  id: string;
  report_type: ReportType;
  period_start: string;
  period_end: string;
  generated_at: string;
  status: string;
  summary_md: string;
}

export interface ReportDetail {
  report: ReportMeta;
  records: Pick<ActivityItem, "machine" | "kind" | "project" | "title" | "summary_text" | "started_at">[];
}

export interface UsageBucket {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  calls: number;
  cost: number; // 美元估算值，展示用 ≈
}

export interface UsageData {
  date?: string;
  start?: string;
  end?: string;
  totals: UsageBucket;
  by_day_machine: (UsageBucket & { date: string; machine: string })[];
  by_model: (UsageBucket & { provider: string; model: string; machine: string })[];
}

/** 按 machine 聚合 by_day_machine（单日查询时每机一条，求和以保证区间查询也正确） */
export function usageByMachine(usage: UsageData): Record<string, UsageBucket> {
  const out: Record<string, UsageBucket> = {};
  for (const r of usage.by_day_machine) {
    const b = (out[r.machine] ??= {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      calls: 0,
      cost: 0,
    });
    b.input_tokens += r.input_tokens;
    b.output_tokens += r.output_tokens;
    b.cache_read_tokens += r.cache_read_tokens;
    b.cache_write_tokens += r.cache_write_tokens;
    b.reasoning_tokens += r.reasoning_tokens;
    b.calls += r.calls;
    b.cost += r.cost;
  }
  return out;
}

// 浏览器端 fetch 带前导 "/" 会忽略 Next basePath，必须显式带 /review 前缀；
// dev 与线上都由 basePath rewrite（/review/api/* → 后端 /api/review/*）承接。
const API = "/review/api";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
  return res.json();
}

export async function apiSend<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string })?.detail || `${method} ${path}: ${res.status}`);
  return data as T;
}

export async function getUsage(params: { date: string } | { start: string; end: string }): Promise<UsageData> {
  const q = new URLSearchParams(params as Record<string, string>).toString();
  return apiGet<UsageData>(`/usage?${q}`);
}

export const MACHINE_META: Record<string, { label: string; dot: string }> = {
  windows: { label: "Windows", dot: "bg-sky-500" },
  nas: { label: "NAS", dot: "bg-emerald-500" },
};

export function machineMeta(machine: string) {
  return MACHINE_META[machine] ?? { label: machine, dot: "bg-gray-400" };
}
