'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  cancelRentalRefresh,
  fetchRentalRefreshJob,
  isTerminalPhase,
  startRentalRefresh,
  type RentalRefreshJob,
} from './rental-types';

export const RENTAL_REFRESH_POLL_INTERVAL_MS = 2000;

export interface UseRentalRefreshResult {
  /** 当前任务状态；null 表示没有已知任务 */
  job: RentalRefreshJob | null;
  /** 任务处于运行/取消中（非终态） */
  running: boolean;
  /** start/cancel 的失败信息（409 冲突、422 无映射等） */
  actionError: string | null;
  start: () => Promise<void>;
  cancel: () => Promise<void>;
}

/**
 * 租金更新任务 hook（design.md "Web refresh"）。
 * - 挂载时 GET 一次恢复任务状态（页面重开可恢复）；
 * - 运行中每 2 秒轮询，终态停止并调用 onSettled（调用方借此重拉摘要与当前详情）；
 * - 卸载清理 interval 与 AbortController。
 */
export function useRentalRefresh(onSettled?: () => void): UseRentalRefreshResult {
  const [job, setJob] = useState<RentalRefreshJob | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const settledRef = useRef(onSettled);
  useEffect(() => { settledRef.current = onSettled; });

  // 挂载恢复：无任务/网络异常都保持"无任务"展示，不阻塞页面
  useEffect(() => {
    const controller = new AbortController();
    fetchRentalRefreshJob(controller.signal)
      .then(restored => {
        if (!controller.signal.aborted) setJob(restored);
      })
      .catch(() => { /* 恢复失败按无任务处理 */ });
    return () => controller.abort();
  }, []);

  const running = job !== null && !isTerminalPhase(job.phase);

  // 运行中每 2 秒轮询；收到终态后停止（running 变 false 触发清理）并通知重拉数据
  useEffect(() => {
    if (!running) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      fetchRentalRefreshJob(controller.signal)
        .then(next => {
          if (controller.signal.aborted) return;
          setJob(next);
          if (next !== null && isTerminalPhase(next.phase)) settledRef.current?.();
        })
        .catch(() => { /* 单次轮询失败忽略，下个周期重试 */ });
    }, RENTAL_REFRESH_POLL_INTERVAL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [running]);

  const start = useCallback(async () => {
    setActionError(null);
    try {
      setJob(await startRentalRefresh());
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '启动租金更新失败');
    }
  }, []);

  const cancel = useCallback(async () => {
    setActionError(null);
    try {
      setJob(await cancelRentalRefresh());
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '取消租金更新失败');
    }
  }, []);

  return { job, running, actionError, start, cancel };
}
