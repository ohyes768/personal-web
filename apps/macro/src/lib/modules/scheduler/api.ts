/**
 * Scheduler 模块 API 封装
 * 所有 scheduler 管理 API 调用必须通过此文件
 * 走 next.config.js 的 /api/macro/:path* rewrite 代理到后端 8094
 */
import { directClient } from '@/lib/api-client';
import type {
  SchedulerJob,
  SchedulerJobRun,
  SchedulerTriggerResponse,
} from '@/lib/modules/scheduler/types';

/** 运行历史响应 */
export interface SchedulerRunsResponse {
  job_id: string;
  runs: SchedulerJobRun[];
  total_returned: number;
}

export const schedulerApi = {
  /**
   * 列出所有调度任务（含 cron / cron_human / enabled / next_run_time / last_run）
   */
  listJobs: () =>
    directClient.get<{ jobs: SchedulerJob[] }>('/api/macro/scheduler/jobs'),

  /**
   * 启用或禁用某个任务（写回后端 scheduler.json）
   */
  setEnabled: (jobId: string, enabled: boolean) =>
    directClient.patch<SchedulerJob>(`/api/macro/scheduler/jobs/${jobId}`, {
      enabled,
    }),

  /**
   * 立即执行某个任务（异步触发，返回后用 getRuns 查结果）
   */
  runNow: (jobId: string) =>
    directClient.post<SchedulerTriggerResponse>(
      `/api/macro/scheduler/jobs/${jobId}/run`
    ),

  /**
   * 查任务最近 N 条执行历史（含数据源子明细 items）
   */
  getRuns: (jobId: string, limit = 20) =>
    directClient.get<SchedulerRunsResponse>(
      `/api/macro/scheduler/jobs/${jobId}/runs`,
      { limit }
    ),
};
