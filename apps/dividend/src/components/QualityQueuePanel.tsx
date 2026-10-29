/**
 * 评级队列面板：集中展示运行中 / 排队中的评级任务与最近终态项。
 * 数据来自服务端逐股快照（per_code），独立于筛选结果与查询条件。
 */
'use client';

import { useEffect, useState } from 'react';
import {
  formatElapsedSince,
  formatElapsedSpan,
  qualityJobActive,
  type QualityJob,
  type QualityQueueRow,
  type QualityQueueView,
} from '@/lib/quality';

const buttonClass = 'rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40';

export interface QualityQueuePanelProps {
  view: QualityQueueView;
  job: QualityJob | null;
  /** 重试失败股票（逐股入口在行内） */
  onRetry: (codes: string[]) => void;
  /** Hermes 未配置时置灰重试 */
  configured: boolean;
}

export function QualityQueuePanel({ view, job, onRetry, configured }: QualityQueuePanelProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const active = view.runningCount + view.queuedCount > 0 || (!!job && qualityJobActive(job));
  // 计时只在有活动任务时每秒刷新；终态定格不再跑定时器
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);

  if (view.rows.length === 0) return null;
  const failedRows = view.rows.filter(row => row.state === 'failed');
  return (
    <div aria-label="评级任务队列" className="rounded-xl border border-rule bg-paper-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">评级任务队列</h3>
        {active && (
          <span className="text-xs text-ink-muted">
            运行 {view.runningCount} · 排队 {view.queuedCount}
            {job && qualityJobActive(job) && ` · 进度 ${job.processed}/${job.total}`}
            {job && qualityJobActive(job) && job.failed > 0 && ` · 曾失败 ${job.failed}`}
          </span>
        )}
        {failedRows.length > 0 && (
          <button
            className={`${buttonClass} ml-auto`}
            disabled={!configured}
            title={configured ? '重新发起失败的评级' : 'Hermes 未配置，无法评级'}
            onClick={() => onRetry(failedRows.map(row => row.code))}
          >
            重试失败 {failedRows.length} 只
          </button>
        )}
      </div>
      <ul className="mt-2 space-y-1">
        {view.rows.map(row => (
          <li key={row.code} className="flex flex-wrap items-baseline gap-2 text-sm">
            <span className="font-medium text-ink">{row.name || row.code}</span>
            <span className="text-xs text-ink-muted">{row.code}</span>
            {row.state === 'running' && (
              <span className="text-xs text-ink-muted animate-pulse">
                评级中 · 已分析 {formatElapsedSince(row.startedAt, nowMs)}
              </span>
            )}
            {row.state === 'queued' && <span className="text-xs text-ink-muted">排队中…</span>}
            {row.state === 'completed' && (
              <span className="text-xs text-emerald-700">完成 · 耗时 {formatElapsedSpan(row.startedAt, row.finishedAt)}</span>
            )}
            {row.state === 'failed' && (
              <span className="inline-flex items-baseline gap-2">
                <span className="text-xs text-red-700" title={row.error || '评级失败'}>
                  失败 · 耗时 {formatElapsedSpan(row.startedAt, row.finishedAt)}
                </span>
                <button
                  className={buttonClass}
                  disabled={!configured}
                  title={configured ? (row.error || '重新发起评级') : 'Hermes 未配置，无法评级'}
                  onClick={() => onRetry([row.code])}
                >
                  重试
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
