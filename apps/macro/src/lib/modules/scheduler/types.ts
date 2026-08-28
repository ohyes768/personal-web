/**
 * Scheduler 模块类型定义
 * 与后端 backend/macro/src/scheduler 的 API 契约对齐（组任务模型）
 */

/**
 * 组任务里单个数据源的子执行结果（每次 POST 一个 /update/* 端点一条）
 */
export interface SchedulerRunItem {
  /** 后端 update 端点路径，如 "/update/china-bonds" */
  path: string;
  status: 'success' | 'failed';
  /** 该数据源返回的数据条数（可能为 null） */
  count: number | null;
  /** 耗时毫秒 */
  ms: number;
  error: string | null;
}

/**
 * 一次任务运行记录（JSONL 历史里的一条）
 */
export interface SchedulerJobRun {
  job_id: string;
  target: string;
  /** 组任务聚合状态：全成功 success / 部分失败 partial / 全失败 failed / 非交易日 skipped */
  status: 'success' | 'partial' | 'failed' | 'skipped';
  /** 成功的数据源个数 */
  count: number | null;
  start: string;
  end?: string | null;
  /** skipped 时的原因（如 non_trading_day） */
  reason?: string | null;
  error?: string | null;
  /** 数据源子明细（组任务逐端点的结果） */
  items?: SchedulerRunItem[];
}

/**
 * list_jobs 返回的精简上次运行（后端 _slim_last_run：仅保留
 * start/end/status/count/reason/error，无 job_id/target/items）
 */
export type SchedulerLastRun = Pick<
  SchedulerJobRun,
  'start' | 'end' | 'status' | 'count' | 'reason' | 'error'
>;

/**
 * 调度任务（GET /api/macro/scheduler/jobs 返回）
 */
export interface SchedulerJob {
  id: string;
  name: string;
  /** job 类型，固定 "run_group"（组任务） */
  target: string;
  cron: string;
  /** cron 中文可读描述，如 "工作日 16:10" */
  cron_human: string;
  enabled: boolean;
  next_run_time?: string | null;
  last_run?: SchedulerLastRun | null;
  description?: string;
}

/**
 * 立即触发响应（POST /api/macro/scheduler/jobs/{id}/run 返回）
 */
export interface SchedulerTriggerResponse {
  job_id: string;
  triggered_at: string;
}
