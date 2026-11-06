/**
 * SchedulerModal — 定时任务管理弹框
 *
 * 展示 douyin-processor 的定时任务（转写 09:45/17:15 + 清理 03:07）：
 * - job 卡片：name / cron 人话 / 下次触发 / enabled 开关 / 立即执行 / 展开历史
 * - 启停：乐观更新 PATCH，失败回滚 + 提示；状态持久化在后端 data/scheduler/enabled.json
 * - 立即执行：DateTrigger 后台跑，3 秒后刷新历史
 * - 历史：最近 20 条，带 手动/定时 trigger 徽章
 *
 * 数据来源：schedulerApi（后端 /api/scheduler/*，经 Next 代理 PATCH/POST/GET）
 * 结构参照 apps/dividend/src/components/SchedulerSettingsModal.tsx，配色沿 douyin 出版物体系
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { schedulerApi } from '@/lib/api';
import type { SchedulerJob, SchedulerJobRun } from '@/lib/types';

const STATUS_META: Record<SchedulerJobRun['status'], { label: string; cls: string }> = {
  success: { label: '成功', cls: 'bg-success/10 text-success border-success/30' },
  skipped: { label: '跳过', cls: 'bg-accent/10 text-accent border-accent/30' },
  failed: { label: '失败', cls: 'bg-danger/10 text-danger border-danger/30' },
};

const TRIGGER_LABEL: Record<SchedulerJobRun['trigger'], string> = {
  scheduled: '定时',
  manual: '手动',
  startup: '启动',
};

function formatTs(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function durationOf(run: Pick<SchedulerJobRun, 'start' | 'end'>): string {
  if (!run.start || !run.end) return '';
  const s = new Date(run.start).getTime();
  const e = new Date(run.end).getTime();
  if (isNaN(s) || isNaN(e) || e < s) return '';
  const ms = e - s;
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${Math.floor(sec / 60)}m${Math.floor(sec % 60)}s`;
}

export function SchedulerModal({ onClose }: { onClose: () => void }) {
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null);

  // 任务级操作锁（防快速连点）
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
    reload();
  }, [reload]);

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
    setToast({ kind: 'success', msg: `${job.name} 已触发，几秒后可刷新历史` });
    try {
      await schedulerApi.runNow(job.id);
      // 3 秒后刷新（该任务已展开时）+ 刷新 last_run
      setTimeout(() => {
        if (expandedId === job.id) reloadRuns(job.id);
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

  const handleToggleExpand = (jobId: string) => {
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
    <div
      className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md p-4 sm:p-6 flex items-start sm:items-center justify-center"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[680px] max-h-[calc(100vh-32px)] sm:max-h-[calc(100vh-48px)] bg-paper rounded-[14px] shadow-[0_24px_64px_rgba(43,42,40,0.18)] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <header className="shrink-0 relative px-6 sm:px-8 pt-7 pb-4 border-b border-rule">
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-9 h-9 border-none bg-paper hover:bg-paper-deep rounded-full text-ink-muted hover:text-ink cursor-pointer text-base flex items-center justify-center transition-all"
            aria-label="关闭"
          >
            ✕
          </button>
          <h2 className="font-serif-cn text-[22px] font-bold text-ink-strong tracking-tight">
            定时任务管理
          </h2>
          <p className="font-ui text-[12px] text-ink-muted mt-1">
            cron 由配置文件（config/app.yaml）固定，UI 仅开放启用/禁用与立即执行；启停状态重启后保持
          </p>
        </header>

        {/* 主体：滚动区 */}
        <div className="flex-1 overflow-y-auto px-6 sm:px-8 py-5 space-y-3">
          {toast && (
            <div
              className={`font-ui px-4 py-2.5 rounded-md text-[13px] border ${
                toast.kind === 'success'
                  ? 'bg-success/10 border-success/30 text-success'
                  : 'bg-danger/10 border-danger/30 text-danger'
              }`}
            >
              {toast.msg}
            </div>
          )}

          {loading && jobs.length === 0 ? (
            <div className="font-ui text-center text-ink-muted py-12 text-[14px]">加载中...</div>
          ) : (
            jobs.map((job) => (
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
            ))
          )}
        </div>
      </div>
    </div>
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
    <div className="border border-rule rounded-lg overflow-hidden bg-paper-card">
      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-ui flex items-center gap-2">
              <span className="text-[15px] font-medium text-ink-strong">{job.name}</span>
              <span className="text-[11px] text-ink-soft">({job.target})</span>
            </div>
            <div className="font-ui text-[12px] text-ink-muted mt-1">
              <code className="bg-paper-deep px-1.5 py-0.5 rounded text-[11px]">
                {job.crons.join(' + ')}
              </code>
              <span className="ml-2">{job.cron_human}</span>
            </div>
            {job.description && (
              <div className="font-ui text-[12px] text-ink-soft mt-0.5">{job.description}</div>
            )}
            <div className="font-ui text-[12px] text-ink-muted mt-1">
              下次: {job.enabled ? <span className="tnum">{formatTs(job.next_run_time)}</span> : <span className="text-ink-soft">（已禁用）</span>}
              {job.last_run && (
                <span className="ml-3">
                  上次:{' '}
                  <span className={STATUS_META[job.last_run.status]?.cls ?? ''}>
                    {STATUS_META[job.last_run.status]?.label ?? job.last_run.status}
                  </span>
                  {job.last_run.trigger && (
                    <span className="ml-1 text-ink-soft">({TRIGGER_LABEL[job.last_run.trigger] ?? job.last_run.trigger})</span>
                  )}
                  {job.last_run.count != null && (
                    <span className="ml-1 tnum">{job.last_run.count}</span>
                  )}
                  {job.last_run.reason && (
                    <span className="ml-1 text-ink-soft">({job.last_run.reason})</span>
                  )}
                </span>
              )}
            </div>
          </div>

          {/* 启停开关 */}
          <label className="inline-flex items-center cursor-pointer shrink-0">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={job.enabled}
              disabled={toggling}
              onChange={onToggle}
            />
            <div
              className={`relative w-10 h-5.5 rounded-full transition-colors ${
                job.enabled ? 'bg-accent' : 'bg-ink-soft'
              } ${toggling ? 'opacity-50' : ''}`}
            >
              <div
                className={`absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-paper-card rounded-full transition-transform ${
                  job.enabled ? 'translate-x-4.5' : 'translate-x-0'
                }`}
              />
            </div>
            <span className="font-ui ml-2 text-[12px] text-ink w-8">
              {job.enabled ? '启用' : '禁用'}
            </span>
          </label>
        </div>

        {/* 操作按钮 */}
        <div className="font-ui flex items-center gap-2 pt-1">
          <button
            onClick={onRun}
            disabled={running}
            className="px-3 py-1.5 rounded-md text-[13px] border border-accent text-accent bg-accent/[0.04] hover:bg-accent hover:text-paper transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {running ? '触发中…' : '立即执行'}
          </button>
          <button
            onClick={onToggleExpand}
            className="px-3 py-1.5 rounded-md text-[13px] border border-rule text-ink hover:border-ink-soft transition-all cursor-pointer"
          >
            {expanded ? '收起历史' : '查看历史'}
          </button>
        </div>
      </div>

      {/* 历史区 */}
      {expanded && (
        <div className="border-t border-rule bg-paper-deep/60 p-4">
          <div className="font-ui flex items-center justify-between mb-2">
            <span className="text-[12px] text-ink-muted">最近 20 条历史（最新在前）</span>
            <button
              onClick={onRefreshRuns}
              className="text-[12px] text-accent hover:underline disabled:opacity-50"
              disabled={runsLoading}
            >
              {runsLoading ? '加载中…' : '刷新'}
            </button>
          </div>
          {runsLoading && !runs ? (
            <div className="font-ui text-center text-ink-soft py-4 text-[12px]">加载中...</div>
          ) : !runs || runs.length === 0 ? (
            <div className="font-ui text-center text-ink-soft py-4 text-[12px]">暂无执行历史</div>
          ) : (
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {runs.map((r, i) => (
                <div
                  key={`${r.start}-${i}`}
                  className="font-ui flex items-start gap-2 text-[12px] py-1.5 border-b border-rule last:border-b-0"
                >
                  <span
                    className={`px-1.5 py-0.5 rounded border ${STATUS_META[r.status]?.cls ?? ''}`}
                  >
                    {STATUS_META[r.status]?.label ?? r.status}
                  </span>
                  <span className="text-ink-soft whitespace-nowrap">{TRIGGER_LABEL[r.trigger] ?? r.trigger}</span>
                  <span className="tnum text-ink-muted whitespace-nowrap">{formatTs(r.start)}</span>
                  {r.end && (
                    <span className="text-ink-soft whitespace-nowrap">{durationOf(r)}</span>
                  )}
                  {r.count != null && <span className="text-ink tnum">{r.count}</span>}
                  {Array.isArray(r.failed) && r.failed.length > 0 && (
                    <span className="text-danger">{r.failed.length} 个文件删除失败</span>
                  )}
                  {typeof r.failed === 'number' && r.failed > 0 && (
                    <span className="text-danger">失败 {r.failed}</span>
                  )}
                  {r.reason && <span className="text-ink-soft">({r.reason})</span>}
                  {r.error && (
                    <span
                      className="text-danger flex-1 min-w-0 truncate"
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
