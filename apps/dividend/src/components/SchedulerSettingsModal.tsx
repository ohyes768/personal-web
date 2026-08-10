/**
 * SchedulerSettingsModal — 定时任务管理弹框
 *
 * 展示 3 个预设任务：
 * - 列表：name / target / cron_human / enabled Switch / 立即执行 / 展开历史
 * - 启用/禁用：立即 PATCH，失败回滚 + 提示
 * - 立即执行：POST 触发，3 秒后异步刷新历史
 * - 展开历史：选中的任务拉最近 20 条（status badge + count + reason/error）
 *
 * 数据来源：schedulerApi（直接调后端 4 个 API）
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { Modal } from './shared-ui/Modal';
import { Button } from './shared-ui/Button';
import { schedulerApi } from '@/lib/api';
import type { SchedulerJob, SchedulerJobRun } from '@/lib/types';

export interface SchedulerSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const STATUS_META: Record<SchedulerJobRun['status'], { label: string; cls: string }> = {
  success: { label: '成功', cls: 'bg-green-900/50 text-green-300 border-green-700' },
  skipped: { label: '跳过', cls: 'bg-yellow-900/50 text-yellow-300 border-yellow-700' },
  failed: { label: '失败', cls: 'bg-red-900/50 text-red-300 border-red-700' },
};

function formatTs(iso?: string | null): string {
  if (!iso) return '-';
  // 形如 "2026-08-05T15:30:00+08:00"
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function durationOf(run: SchedulerJobRun): string {
  if (!run.start || !run.end) return '';
  const s = new Date(run.start).getTime();
  const e = new Date(run.end).getTime();
  if (isNaN(s) || isNaN(e) || e < s) return '';
  const ms = e - s;
  if (ms < 1000) return `${ms}ms`;
  const s_show = ms / 1000;
  if (s_show < 60) return `${s_show.toFixed(1)}s`;
  return `${Math.floor(s_show / 60)}m${Math.floor(s_show % 60)}s`;
}

export function SchedulerSettingsModal({ isOpen, onClose }: SchedulerSettingsModalProps) {
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null);

  // 任务级状态：每个 job 一个"切换中"锁（防快速连点）
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  // 当前展开历史的任务 id
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runsById, setRunsById] = useState<Record<string, SchedulerJobRun[]>>({});
  const [runsLoading, setRunsLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await schedulerApi.listJobs();
      setJobs(resp.jobs);
    } catch (e) {
      setToast({ kind: 'error', msg: e instanceof Error ? e.message : '加载任务失败' });
    } finally {
      setLoading(false);
    }
  }, []);

  // 打开时拉一次
  useEffect(() => {
    if (isOpen) {
      reload();
      setToast(null);
    }
  }, [isOpen, reload]);

  // 立即执行某个任务后，3 秒轮询 1 次历史（如果展开中）
  const reloadRuns = useCallback(async (jobId: string) => {
    setRunsLoading(true);
    try {
      const resp = await schedulerApi.getRuns(jobId, 20);
      setRunsById((prev) => ({ ...prev, [jobId]: resp.runs }));
    } catch (e) {
      setToast({ kind: 'error', msg: e instanceof Error ? e.message : '加载历史失败' });
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const handleToggle = async (job: SchedulerJob, nextEnabled: boolean) => {
    if (togglingIds.has(job.id)) return;
    setTogglingIds((s) => new Set(s).add(job.id));
    // 乐观更新
    setJobs((prev) => prev.map((j) => (j.id === job.id ? { ...j, enabled: nextEnabled } : j)));
    try {
      const updated = await schedulerApi.setEnabled(job.id, nextEnabled);
      setJobs((prev) => prev.map((j) => (j.id === job.id ? updated : j)));
      setToast({ kind: 'success', msg: `${job.name} 已${nextEnabled ? '启用' : '禁用'}` });
    } catch (e) {
      // 失败回滚
      setJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)));
      setToast({ kind: 'error', msg: e instanceof Error ? e.message : '切换失败' });
    } finally {
      setTogglingIds((s) => {
        const ns = new Set(s);
        ns.delete(job.id);
        return ns;
      });
    }
  };

  const handleRun = async (job: SchedulerJob) => {
    if (runningIds.has(job.id)) return;
    setRunningIds((s) => new Set(s).add(job.id));
    setToast({ kind: 'success', msg: `${job.name} 已触发，几秒后刷新历史` });
    try {
      await schedulerApi.runNow(job.id);
      // 3 秒后刷新历史（如果该任务已展开）
      setTimeout(() => {
        if (expandedId === job.id) reloadRuns(job.id);
        // 刷新顶部 last_run
        reload();
      }, 3000);
    } catch (e) {
      setToast({ kind: 'error', msg: e instanceof Error ? e.message : '触发失败' });
    } finally {
      setRunningIds((s) => {
        const ns = new Set(s);
        ns.delete(job.id);
        return ns;
      });
    }
  };

  const handleToggleExpand = async (jobId: string) => {
    if (expandedId === jobId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(jobId);
    if (!runsById[jobId]) {
      reloadRuns(jobId);
    }
  };

  // Toast 3 秒自动消失
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="定时任务管理" size="lg">
      <div className="space-y-4">
        {toast && (
          <div
            className={`px-4 py-2 rounded text-sm border ${
              toast.kind === 'success'
                ? 'bg-green-900/50 border-green-700 text-green-200'
                : 'bg-red-900/50 border-red-700 text-red-200'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="text-xs text-gray-400 bg-gray-800/40 border border-gray-700 rounded px-3 py-2">
          替代外部 n8n 定时触发。cron 由配置文件固定，UI 仅开放启用/禁用与立即执行。
        </div>

        {loading && jobs.length === 0 ? (
          <div className="text-center text-gray-400 py-12">加载中...</div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                toggling={togglingIds.has(job.id)}
                running={runningIds.has(job.id)}
                expanded={expandedId === job.id}
                runs={runsById[job.id]}
                runsLoading={runsLoading && expandedId === job.id}
                onToggle={() => handleToggle(job, !job.enabled)}
                onRun={() => handleRun(job)}
                onToggleExpand={() => handleToggleExpand(job.id)}
                onRefreshRuns={() => reloadRuns(job.id)}
              />
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}

interface JobCardProps {
  job: SchedulerJob;
  toggling: boolean;
  running: boolean;
  expanded: boolean;
  runs?: SchedulerJobRun[];
  runsLoading: boolean;
  onToggle: () => void;
  onRun: () => void;
  onToggleExpand: () => void;
  onRefreshRuns: () => void;
}

function JobCard({
  job,
  toggling,
  running,
  expanded,
  runs,
  runsLoading,
  onToggle,
  onRun,
  onToggleExpand,
  onRefreshRuns,
}: JobCardProps) {
  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden bg-gray-800/30">
      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-100">{job.name}</span>
              <span className="text-xs text-gray-500">({job.target})</span>
            </div>
            <div className="text-xs text-gray-400 mt-1">
              cron: <code className="bg-gray-700 px-1.5 py-0.5 rounded">{job.cron}</code>
              <span className="ml-2">{job.cron_human}</span>
            </div>
            {job.description && (
              <div className="text-xs text-gray-500 mt-1">{job.description}</div>
            )}
            <div className="text-xs text-gray-400 mt-1">
              下次: {job.enabled ? formatTs(job.next_run_time) : <span className="text-gray-500">（已禁用）</span>}
              {job.last_run && (
                <span className="ml-3">
                  上次:{' '}
                  <span className={STATUS_META[job.last_run.status]?.cls ?? ''}>
                    {STATUS_META[job.last_run.status]?.label ?? job.last_run.status}
                  </span>
                  {job.last_run.count != null && (
                    <span className="ml-1 text-gray-500">{job.last_run.count} 只</span>
                  )}
                  {job.last_run.reason && (
                    <span className="ml-1 text-gray-500">({job.last_run.reason})</span>
                  )}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={job.enabled}
                disabled={toggling}
                onChange={onToggle}
              />
              <div
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  job.enabled ? 'bg-blue-600' : 'bg-gray-600'
                } ${toggling ? 'opacity-50' : ''}`}
              >
                <div
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                    job.enabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </div>
              <span className="ml-2 text-xs text-gray-300 w-8">
                {job.enabled ? '启用' : '禁用'}
              </span>
            </label>
          </div>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <Button
            onClick={onRun}
            disabled={running}
            className="bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 text-sm px-3 py-1.5"
          >
            {running ? '触发中…' : '立即执行'}
          </Button>
          <Button
            onClick={onToggleExpand}
            className="border border-gray-500 bg-transparent text-gray-200 hover:bg-gray-700/60 text-sm px-3 py-1.5"
          >
            {expanded ? '收起历史' : '查看历史'}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-700 bg-gray-900/40 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">最近 20 条历史（最新在前）</span>
            <button
              onClick={onRefreshRuns}
              className="text-xs text-blue-400 hover:underline"
              disabled={runsLoading}
            >
              {runsLoading ? '加载中…' : '刷新'}
            </button>
          </div>
          {runsLoading && !runs ? (
            <div className="text-center text-gray-500 py-4 text-xs">加载中...</div>
          ) : !runs || runs.length === 0 ? (
            <div className="text-center text-gray-500 py-4 text-xs">暂无执行历史</div>
          ) : (
            <div className="space-y-1 max-h-80 overflow-y-auto">
              {runs.map((r, i) => (
                <div
                  key={`${r.start}-${i}`}
                  className="flex items-start gap-2 text-xs py-1.5 border-b border-gray-800 last:border-b-0"
                >
                  <span
                    className={`px-1.5 py-0.5 rounded border ${STATUS_META[r.status]?.cls ?? ''}`}
                  >
                    {STATUS_META[r.status]?.label ?? r.status}
                  </span>
                  <span className="text-gray-400 whitespace-nowrap">{formatTs(r.start)}</span>
                  {r.end && (
                    <span className="text-gray-500 whitespace-nowrap">{durationOf(r)}</span>
                  )}
                  {r.count != null && (
                    <span className="text-gray-300">{r.count} 只</span>
                  )}
                  {r.reason && (
                    <span className="text-gray-500">({r.reason})</span>
                  )}
                  {r.error && (
                    <span
                      className="text-red-300 flex-1 min-w-0 truncate"
                      title={r.error}
                      onClick={() => navigator.clipboard?.writeText(r.error || '')}
                      style={{ cursor: 'pointer' }}
                    >
                      {r.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
