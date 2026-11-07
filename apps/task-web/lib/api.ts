export const API = "/api/task-web";

export type RunStatus =
  | "waiting" | "running" | "success" | "failed"
  | "timeout" | "interrupted" | "skipped";

export interface Run {
  run_id: string;
  task_id: string;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  trigger: "manual" | "scheduled";
  status: RunStatus;
  exit_code: number | null;
  missed_schedule_at: string | null;
}

export interface TaskView {
  id: string;
  name: string;
  description: string;
  command: string;
  cwd: string;
  cron: string;
  enabled: boolean;
  timeout_seconds: number;
  group: "script" | "ai";
  profile: string | null;
  targets: ("dingtalk" | "wechat" | "rss" | "web")[];
  last_run: Run | null;
  active_run: Run | null;
  next_fire_time: string | null;
}

export interface ScheduleSummaryDay {
  date: string;
  total: number;
  missed: number;
  waiting: number;
  running: number;
  success: number;
  failed: number;
  timeout: number;
  interrupted: number;
  skipped: number;
}

export interface ScheduleSlot {
  at: string;
  kind: "run" | "planned" | "pending";
  run?: Run;
}

export interface ScheduleTaskView {
  id: string;
  name: string;
  group: "script" | "ai";
  cron: string;
  enabled: boolean;
  cron_valid: boolean;
  slots: ScheduleSlot[];
  manual: { at: string; run: Run }[];
}

export interface ScheduleDayView {
  date: string;
  tasks: ScheduleTaskView[];
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
  return res.json();
}

export async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `${method} ${path}: ${res.status}`);
  return data as T;
}

export function statusLabel(s: string): string {
  const map: Record<string, string> = {
    waiting: "等待", running: "运行中", success: "成功", failed: "失败",
    timeout: "超时", interrupted: "中断", skipped: "跳过",
  };
  return map[s] ?? s;
}

export function statusColor(s: string): string {
  const map: Record<string, string> = {
    waiting: "#d97706", running: "#2563eb", success: "#16a34a",
    failed: "#dc2626", timeout: "#ea580c", interrupted: "#7c3aed", skipped: "#6b7280",
  };
  return map[s] ?? "#374151";
}
