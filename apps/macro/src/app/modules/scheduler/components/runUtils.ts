/**
 * Scheduler 运行记录的共享展示工具
 * JobCard（上次运行）与 RunsHistory（历史列表）共用，避免两处各写一份状态语义
 */
import type { SchedulerJobRun } from '@/lib/modules/scheduler/types';

/** 状态徽标：成功绿 / 跳过与部分失败黄 / 失败红（沿用股息率前端已验证配色） */
export const STATUS_META: Record<SchedulerJobRun['status'], { label: string; cls: string }> = {
  success: { label: '成功', cls: 'bg-green-900/50 text-green-300 border-green-700' },
  partial: { label: '部分失败', cls: 'bg-yellow-900/50 text-yellow-300 border-yellow-700' },
  skipped: { label: '跳过', cls: 'bg-yellow-900/50 text-yellow-300 border-yellow-700' },
  failed: { label: '失败', cls: 'bg-red-900/50 text-red-300 border-red-700' },
};

/** ISO 时间 → "YYYY-MM-DD HH:mm"（本地时区） */
export function formatTs(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** start/end → 可读耗时（"450ms" / "3.2s" / "1m05s"） */
export function durationOf(run: Pick<SchedulerJobRun, 'start' | 'end'>): string {
  if (!run.start || !run.end) return '';
  const s = new Date(run.start).getTime();
  const e = new Date(run.end).getTime();
  if (isNaN(s) || isNaN(e) || e < s) return '';
  const ms = e - s;
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${Math.floor(sec / 60)}m${String(Math.floor(sec % 60)).padStart(2, '0')}s`;
}
