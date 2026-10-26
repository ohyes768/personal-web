/**
 * useQualityAnalysis — 基本面评级（Hermes 五维）的加载 / 提交 / 轮询
 *
 * 从 ScreeningTab 的内联逻辑原样抽出：列表、个股详情弹框、评级弹框共用同一份
 * 轮询状态，关掉弹框不会中断已提交的 job。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendApi } from '@/lib/api';
import { qualityFinishMessage, qualityJobActive, type QualityJob, type QualityPerCodeMap, type QualityScoresResponse } from '@/lib/quality';

export interface UseQualityAnalysisResult {
  /** 已落盘评级：code → 评分 */
  qualityScores: QualityScoresResponse['scores'];
  /** 逐股实时状态：code → queued/running/completed/failed（含失败原因） */
  qualityPerCode: QualityPerCodeMap;
  /** Hermes 是否已配置；false 时前端置灰分析入口 */
  qualityConfigured: boolean;
  /** 是否有评级任务在跑 */
  analyzing: boolean;
  /** 当前评级任务（用于展示进度） */
  qualityJob: QualityJob | null;
  /** 任务结果/错误提示 */
  qualityMessage: string;
  /** 提交评级分析（异步 job） */
  analyze: (codes: string[]) => Promise<void>;
  /** 重新拉取已落盘评级 */
  refreshScores: () => Promise<void>;
}

export function useQualityAnalysis(): UseQualityAnalysisResult {
  const [qualityScores, setQualityScores] = useState<QualityScoresResponse['scores']>({});
  const [qualityPerCode, setQualityPerCode] = useState<QualityPerCodeMap>({});
  const [qualityConfigured, setQualityConfigured] = useState(true);
  const [qualityJob, setQualityJob] = useState<QualityJob | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [qualityMessage, setQualityMessage] = useState('');
  const requestId = useRef(0);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshScores = useCallback(async (id: number) => {
    try {
      const response = await dividendApi.getQualityScores();
      if (id === requestId.current) {
        setQualityScores(response.scores ?? {});
        setQualityPerCode(response.per_code ?? {});
        // 旧后端缺 hermes_configured 字段时不置灰：点了会得到明确 503 提示，好过莫名禁用
        setQualityConfigured(response.hermes_configured !== false);
      }
    } catch { /* 拉取失败保持现状，表格列显示「待分析」，点分析时会得到明确报错 */ }
  }, []);

  // 首屏并行加载评级（与筛选结果互不阻塞）
  useEffect(() => {
    void refreshScores(requestId.current);
    return () => {
      requestId.current++;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [refreshScores]);

  const analyze = useCallback(async (codes: string[]) => {
    if (!codes.length) return;
    const id = ++requestId.current;
    setAnalyzing(true);
    setQualityMessage('');
    try {
      const job = await dividendApi.analyzeQuality(codes);
      if (id !== requestId.current) return;
      setQualityJob(job);
      const poll = async () => {
        if (id !== requestId.current) return;
        let latest: QualityJob;
        try {
          latest = await dividendApi.getQualityJob(job.job_id);
        } catch (err) {
          if (id === requestId.current) {
            setAnalyzing(false);
            setQualityMessage(err instanceof Error ? err.message : '查询评级进度失败');
          }
          return;
        }
               if (id !== requestId.current) return;
        setQualityJob(latest);
        if (latest.per_code) setQualityPerCode(latest.per_code);
        if (qualityJobActive(latest)) {
          pollTimer.current = setTimeout(() => void poll(), 3000);
          return;
        }
        setAnalyzing(false);
        await refreshScores(id);
        setQualityMessage(qualityFinishMessage(latest));
      };
      void poll();
    } catch (err) {
      if (id === requestId.current) {
        setAnalyzing(false);
        setQualityJob(null);
        setQualityMessage(err instanceof Error ? err.message : '提交评级失败');
      }
    }
  }, [refreshScores]);

  return { qualityScores, qualityPerCode, qualityConfigured, analyzing, qualityJob, qualityMessage, analyze, refreshScores: () => refreshScores(requestId.current) };
}
