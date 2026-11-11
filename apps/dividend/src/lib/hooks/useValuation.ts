/**
 * useValuation — 收藏跟踪四挡位估值的加载 / 提交 / 轮询
 *
 * 单一轮询生命周期：挂载时重新发现最新 valuation job（刷新页面恢复队列），
 * 追加提交复用同一轮询，查询失败保留状态并自动重试。模式同 useQualityAnalysis。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendApi, dividendUpdateApi } from '@/lib/api';
import { ApiHttpError } from '@/lib/api-client';
import {
  isValuationJobActive,
  type ValuationJob,
  type ValuationMoveAction,
  type ValuationPerCodeMap,
  type ValuationReportRecord,
  type ValuationStatusResponse,
} from '@/lib/valuation';

const POLL_INTERVAL_MS = 3000;

export interface UseValuationResult {
  /** 已落盘估值报告：code → 记录 */
  reports: Record<string, ValuationReportRecord>;
  /** 逐股实时状态：code → queued/running/completed/failed */
  perCode: ValuationPerCodeMap;
  /** Hermes 是否已配置；false 时前端置灰评估入口 */
  configured: boolean;
  /** 当前已部署 skill 版本（用于提示需重评） */
  currentSkillVersion: string | null;
  /** 当前估值任务（用于展示进度） */
  job: ValuationJob | null;
  /** 任务结果/错误提示 */
  message: string;
  /** 进度查询暂时失败（任务不受影响，自动重试中） */
  pollError: string;
  /** 提交估值（任务运行中追加入队） */
  analyze: (codes: string[]) => Promise<void>;
  /** 重新拉取全部报告与状态 */
  refresh: () => Promise<void>;
  /** 取消这一次估值。返回空字符串表示已按服务端快照更新；否则是要展示的失败原因。 */
  cancelQueueItem: (itemId: string) => Promise<string>;
  /** 调整等待顺序。冲突时仍会刷成服务端快照。 */
  moveQueueItem: (itemId: string, action: ValuationMoveAction) => Promise<string>;
}

export function useValuation(): UseValuationResult {
  const [reports, setReports] = useState<Record<string, ValuationReportRecord>>({});
  const [perCode, setPerCode] = useState<ValuationPerCodeMap>({});
  const [configured, setConfigured] = useState(true);
  const [currentSkillVersion, setCurrentSkillVersion] = useState<string | null>(null);
  const [job, setJob] = useState<ValuationJob | null>(null);
  const [message, setMessage] = useState('');
  const [pollError, setPollError] = useState('');
  const pollJobId = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const response: ValuationStatusResponse = await dividendApi.getValuationStatus();
      if (!mounted.current) return;
      setReports(response.reports ?? {});
      setCurrentSkillVersion(response.current_skill_version ?? null);
      setConfigured(response.hermes_configured !== false);
      // 逐股实时状态以 job 轮询为准；这里仅在尚无状态时做首屏快照
      setPerCode(prev => (Object.keys(prev).length > 0 ? prev : response.per_code ?? {}));
    } catch { /* 拉取失败保持现状；行内按钮提交时会得到明确报错 */ }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const handleTerminal = useCallback(async (finished: ValuationJob) => {
    stopPolling();
    pollJobId.current = null;
    if (!mounted.current) return;
    setPollError('');
    await refresh();
    if (!mounted.current) return;
    const failed = finished.failed_codes?.length ?? 0;
    if (finished.status === 'succeeded') {
      setMessage(finished.processed > 1 ? `估值完成，共 ${finished.processed} 只` : '');
    } else if (finished.status === 'partial_failed' || finished.status === 'failed') {
      setMessage(`估值完成，失败 ${failed} 只`);
    } else {
      setMessage(`估值任务 ${finished.status === 'interrupted' ? '已中断' : '已结束'}，请重试`);
    }
  }, [refresh, stopPolling]);

  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollJobId.current = jobId;
    const poll = async () => {
      if (!mounted.current || pollJobId.current !== jobId) return;
      let latest: ValuationJob;
      try {
        latest = await dividendApi.getValuationJob(jobId);
      } catch (err) {
        // 查询失败不代表分析结束：保留既有状态，继续自动重试
        if (mounted.current) {
          setPollError(err instanceof Error ? err.message : '查询估值进度失败，自动重试中');
          pollTimer.current = setTimeout(() => void poll(), POLL_INTERVAL_MS);
        }
        return;
      }
      if (!mounted.current || pollJobId.current !== jobId) return;
      setPollError('');
      setJob(latest);
      if (latest.per_code) setPerCode(latest.per_code);
      if (isValuationJobActive(latest)) {
        pollTimer.current = setTimeout(() => void poll(), POLL_INTERVAL_MS);
        return;
      }
      await handleTerminal(latest);
    };
    pollTimer.current = setTimeout(() => void poll(), 0);
  }, [handleTerminal, stopPolling]);

  // 挂载：加载已落盘报告，并重新发现服务器上仍在进行的 valuation 任务
  useEffect(() => {
    mounted.current = true;
    void refresh();
    void (async () => {
      try {
        const latest = await dividendUpdateApi.getLatestRefreshJob('valuation');
        const discovered = latest && latest.kind === 'valuation' ? (latest as ValuationJob) : null;
        if (discovered && isValuationJobActive(discovered)) {
          setJob(discovered);
          startPolling(discovered.job_id);
        }
      } catch { /* 发现失败不影响首屏；提交或下次轮询会再触发 */ }
    })();
    return () => {
      mounted.current = false;
      stopPolling();
    };
  }, [refresh, startPolling, stopPolling]);

  const applyQueueResult = useCallback(async (work: () => Promise<{ per_code?: ValuationPerCodeMap }>) => {
    try {
      const snapshot = await work();
      if (mounted.current && snapshot.per_code) setPerCode(snapshot.per_code);
      return '';
    } catch (err) {
      const body = err instanceof ApiHttpError ? err.body : null;
      const record = body && typeof body === 'object' ? body as { per_code?: ValuationPerCodeMap; detail?: { per_code?: ValuationPerCodeMap } } : null;
      const perCode = record?.per_code ?? record?.detail?.per_code;
      if (mounted.current && perCode) setPerCode(perCode);
      return err instanceof Error ? err.message : '队列操作失败';
    }
  }, []);

  const cancelQueueItem = useCallback(
    (itemId: string) => applyQueueResult(() => dividendApi.cancelValuationItem(itemId)),
    [applyQueueResult],
  );
  const moveQueueItem = useCallback(
    (itemId: string, action: ValuationMoveAction) => applyQueueResult(() => dividendApi.moveValuationItem(itemId, action)),
    [applyQueueResult],
  );

  const analyze = useCallback(async (codes: string[]) => {
    if (!codes.length) return;
    setMessage('');
    try {
      const accepted = await dividendApi.analyzeValuation(codes);
      if (!mounted.current) return;
      if (accepted.per_code) setPerCode(accepted.per_code);
      if (pollJobId.current === accepted.job_id) return; // 追加受理：现有轮询不动
      setJob(accepted);
      if (isValuationJobActive(accepted)) {
        startPolling(accepted.job_id);
      } else {
        await handleTerminal(accepted);
      }
    } catch (err) {
      if (mounted.current) setMessage(err instanceof Error ? err.message : '提交估值失败');
    }
  }, [handleTerminal, startPolling]);

  return {
    reports, perCode, configured, currentSkillVersion, job, message, pollError,
    analyze, refresh, cancelQueueItem, moveQueueItem,
  };
}
