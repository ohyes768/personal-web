/**
 * useQualityAnalysis — 基本面评级（Hermes 五维）的加载 / 提交 / 轮询
 *
 * 单一轮询生命周期：挂载时重新发现最新 quality job（刷新页面恢复队列），
 * 追加提交复用同一轮询，查询失败保留状态并自动重试（查询失败不代表分析结束）。
 * 卸载只取消本地定时器。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendApi, dividendUpdateApi } from '@/lib/api';
import { qualityFinishMessage, qualityJobActive, type QualityJob, type QualityPerCodeMap, type QualityScoresResponse } from '@/lib/quality';

const POLL_INTERVAL_MS = 3000;

export interface UseQualityAnalysisResult {
  currentSkillVersion: string | null;
  /** 已落盘评级：code → 评分 */
  qualityScores: QualityScoresResponse['scores'];
  /** 逐股实时状态：code → queued/running/completed/failed（含名称与生命周期时间戳） */
  qualityPerCode: QualityPerCodeMap;
  /** Hermes 是否已配置；false 时前端置灰分析入口 */
  qualityConfigured: boolean;
  /** 当前评级任务（用于展示进度） */
  qualityJob: QualityJob | null;
  /** 任务结果/错误提示 */
  qualityMessage: string;
  /** 进度查询暂时失败（分析不受影响，自动重试中） */
  qualityPollError: string;
  /** 提交评级分析（任务运行中追加入队） */
  analyze: (codes: string[]) => Promise<void>;
  /** 重新拉取已落盘评级 */
  refreshScores: () => Promise<void>;
}

export function useQualityAnalysis(): UseQualityAnalysisResult {
  const [currentSkillVersion, setCurrentSkillVersion] = useState<string | null>(null);
  const [qualityScores, setQualityScores] = useState<QualityScoresResponse['scores']>({});
  const [qualityPerCode, setQualityPerCode] = useState<QualityPerCodeMap>({});
  const [qualityConfigured, setQualityConfigured] = useState(true);
  const [qualityJob, setQualityJob] = useState<QualityJob | null>(null);
  const [qualityMessage, setQualityMessage] = useState('');
  const [qualityPollError, setQualityPollError] = useState('');
  const pollJobId = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const refreshScores = useCallback(async () => {
    try {
      const response = await dividendApi.getQualityScores();
      if (!mounted.current) return;
      setQualityScores(response.scores ?? {});
      setCurrentSkillVersion(response.current_skill_version ?? null);
      // 逐股实时状态以 job 轮询为准；这里仅在尚无状态时做首屏快照
      setQualityPerCode(prev => (Object.keys(prev).length > 0 ? prev : response.per_code ?? {}));
      setQualityConfigured(response.hermes_configured !== false);
    } catch { /* 拉取失败保持现状，表格列显示「待分析」，点分析时会得到明确报错 */ }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const handleTerminal = useCallback(async (job: QualityJob) => {
    stopPolling();
    pollJobId.current = null;
    if (!mounted.current) return;
    setQualityPollError('');
    await refreshScores();
    if (mounted.current) setQualityMessage(qualityFinishMessage(job));
  }, [refreshScores, stopPolling]);

  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollJobId.current = jobId;
    const poll = async () => {
      if (!mounted.current || pollJobId.current !== jobId) return;
      let latest: QualityJob;
      try {
        latest = await dividendApi.getQualityJob(jobId);
      } catch (err) {
        // 查询失败不代表分析结束：保留既有状态，继续自动重试
        if (mounted.current) {
          setQualityPollError(err instanceof Error ? err.message : '查询评级进度失败，自动重试中');
          pollTimer.current = setTimeout(() => void poll(), POLL_INTERVAL_MS);
        }
        return;
      }
      if (!mounted.current || pollJobId.current !== jobId) return;
      setQualityPollError('');
      setQualityJob(latest);
      if (latest.per_code) setQualityPerCode(latest.per_code);
      if (qualityJobActive(latest)) {
        pollTimer.current = setTimeout(() => void poll(), POLL_INTERVAL_MS);
        return;
      }
      await handleTerminal(latest);
    };
    pollTimer.current = setTimeout(() => void poll(), 0);
  }, [handleTerminal, stopPolling]);

  // 挂载：加载已落盘评级，并重新发现服务器上仍在进行的 quality 任务
  useEffect(() => {
    mounted.current = true;
    void refreshScores();
    void (async () => {
      try {
        const latest = await dividendUpdateApi.getLatestRefreshJob('quality');
        const discovered = latest && latest.kind === 'quality' ? (latest as QualityJob) : null;
        if (discovered && qualityJobActive(discovered)) {
          setQualityJob(discovered);
          startPolling(discovered.job_id);
        }
      } catch { /* 发现失败不影响首屏；提交或下次轮询会再触发 */ }
    })();
    return () => {
      mounted.current = false;
      stopPolling();
    };
  }, [refreshScores, startPolling]);

  const analyze = useCallback(async (codes: string[]) => {
    if (!codes.length) return;
    setQualityMessage('');
    try {
      const job = await dividendApi.analyzeQuality(codes);
      if (!mounted.current) return;
      if (job.per_code) setQualityPerCode(job.per_code);
      if (pollJobId.current === job.job_id) return; // 追加受理：现有轮询不动
      setQualityJob(job);
      if (qualityJobActive(job)) {
        startPolling(job.job_id);
      } else {
        await handleTerminal(job);
      }
    } catch (err) {
      if (mounted.current) setQualityMessage(err instanceof Error ? err.message : '提交评级失败');
    }
  }, [handleTerminal, startPolling]);

  return {
    currentSkillVersion,
    qualityScores,
    qualityPerCode,
    qualityConfigured,
    qualityJob,
    qualityMessage,
    qualityPollError,
    analyze,
    refreshScores,
  };
}
