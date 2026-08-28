'use client';

/**
 * 任务卡片 — 单个调度任务的展示与操作
 * 名称/描述/cron 中文/下次运行/上次运行 + 启停 Switch + 立即执行 + 展开运行历史
 */
import type { SchedulerJob, SchedulerJobRun } from '@/lib/modules/scheduler/types';
import { RunsHistory } from './RunsHistory';
import { STATUS_META, formatTs } from './runUtils';

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

export function JobCard({
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
    <div className="border border-gray-800 rounded-lg overflow-hidden bg-gray-900">
      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-100">{job.name}</span>
              {!job.enabled && (
                <span className="text-xs text-gray-500 border border-gray-700 rounded px-1.5 py-0.5">
                  已禁用
                </span>
              )}
            </div>
            {job.description && (
              <div className="text-xs text-gray-500 mt-1">{job.description}</div>
            )}
            <div className="text-xs text-gray-400 mt-1">
              <code className="bg-gray-800 px-1.5 py-0.5 rounded text-gray-300">{job.cron}</code>
              <span className="ml-2">{job.cron_human}</span>
            </div>
            <div className="text-xs text-gray-400 mt-1">
              下次: {job.enabled ? formatTs(job.next_run_time) : <span className="text-gray-500">（已禁用）</span>}
              {job.last_run && (
                <span className="ml-3">
                  上次:{' '}
                  <span className={`px-1.5 py-0.5 rounded border ${STATUS_META[job.last_run.status]?.cls ?? ''}`}>
                    {STATUS_META[job.last_run.status]?.label ?? job.last_run.status}
                  </span>
                  <span className="ml-1 text-gray-500">{formatTs(job.last_run.start)}</span>
                  {job.last_run.count != null && (
                    <span className="ml-1 text-gray-500">{job.last_run.count} 成功</span>
                  )}
                  {job.last_run.reason && (
                    <span className="ml-1 text-gray-500">({job.last_run.reason})</span>
                  )}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            {/* 启停 Switch（checkbox + peer 样式，沿用股息率已验证实现） */}
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
          <button
            onClick={onRun}
            disabled={running}
            className="bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 text-sm px-3 py-1.5 rounded-lg transition-colors"
          >
            {running ? '触发中…' : '立即执行'}
          </button>
          <button
            onClick={onToggleExpand}
            className="text-sm px-3 py-1.5 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors"
          >
            {expanded ? '收起历史' : '查看历史'}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-800 bg-black/40 p-4">
          <RunsHistory
            runs={runs}
            loading={runsLoading}
            onRefresh={onRefreshRuns}
          />
        </div>
      )}
    </div>
  );
}
