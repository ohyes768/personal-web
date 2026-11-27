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

export interface TodayData {
  date: string;
  items: ActivityItem[];
}

export interface ProjectSummary {
  project: string;
  last_active_at: string;
  session_count: number;
  commit_count: number;
  recent: string[]; // 近期工作摘要
}

export type ReportType = "daily" | "weekly";

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

const API = "/api";

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

export const MACHINE_META: Record<string, { label: string; dot: string }> = {
  windows: { label: "Windows", dot: "bg-sky-500" },
  nas: { label: "NAS", dot: "bg-emerald-500" },
};

export function machineMeta(machine: string) {
  return MACHINE_META[machine] ?? { label: machine, dot: "bg-gray-400" };
}
