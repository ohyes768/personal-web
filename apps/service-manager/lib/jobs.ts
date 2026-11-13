"use client";

/** 刷新任务的后端是异步跑的：提交后拿 job_id，轮询到终态才算完。 */

import { api, type JobState, type RefreshJobView } from "@/lib/api";

/** 终态：任务不会再变化，可以停止轮询。 */
const TERMINAL: ReadonlySet<JobState> = new Set<JobState>([
  "completed",
  "partial_failed",
  "failed",
  "interrupted",
]);

export function isTerminal(state: JobState): boolean {
  return TERMINAL.has(state);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface WaitOptions {
  /** 轮询间隔，默认 1.2s */
  intervalMs?: number;
  /** 最长等待，默认 190s（后端任务自身 180s 超时，留一点余量） */
  timeoutMs?: number;
  /** 组件卸载时中止，停止继续轮询 */
  signal?: AbortSignal;
}

export interface WaitResult {
  /** 最后一次拿到的任务视图（一次都没拿到时为 null） */
  job: RefreshJobView | null;
  /** true：到时限仍未进终态，任务多半还在后台跑 */
  timedOut: boolean;
  /** true：中途被中止（组件卸载） */
  aborted: boolean;
}

/** 轮询一个刷新任务直到终态。 */
export async function waitForJob(jobId: string, options: WaitOptions = {}): Promise<WaitResult> {
  const interval = options.intervalMs ?? 1200;
  const deadline = Date.now() + (options.timeoutMs ?? 190_000);
  let job: RefreshJobView | null = null;

  while (Date.now() < deadline) {
    if (options.signal?.aborted) return { job, timedOut: false, aborted: true };
    try {
      job = await api.job(jobId);
      if (isTerminal(job.state)) return { job, timedOut: false, aborted: false };
    } catch {
      // 单次查询失败不代表任务失败，继续轮询到时限
    }
    await sleep(interval);
  }
  return { job, timedOut: true, aborted: Boolean(options.signal?.aborted) };
}

/** 把终态翻译成一句人话（Toast 里用）。 */
export function describeJob(label: string, job: RefreshJobView): string {
  if (job.state === "interrupted") return `${label}被中断`;
  if (job.state !== "completed" && job.state !== "partial_failed") {
    return `${label}失败${job.error ? `：${job.error}` : ""}`;
  }
  // 容器扫描整体算一次，不按条目数报
  if (job.kind === "docker") {
    return job.state === "completed" ? `${label}完成` : `${label}部分失败`;
  }
  const counts = job.counts ?? {};
  const parts = [`成功 ${counts.succeeded ?? 0}`, `失败 ${counts.failed ?? 0}`];
  if (counts.skipped) parts.push(`跳过 ${counts.skipped}`);
  const tail = `（${parts.join(" · ")}）`;
  return job.state === "completed" ? `${label}完成${tail}` : `${label}部分失败${tail}`;
}
