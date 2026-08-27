/**
 * 定时任务管理页 — 路由 /scheduler（basePath 下实际为 /macro/scheduler）
 *
 * 与股息率的弹框（SchedulerSettingsModal）不同，这里是独立页面：
 * - 任务卡片：cron 中文 / 下次运行 / 上次运行 / 启停 Switch / 立即执行
 * - 点卡片展开运行历史（最近 20 条），每条再展开数据源子明细
 * - 交互沿用股息率已验证模式：启停乐观更新 + 失败回滚；立即执行 3s 后延时刷新；Set 防连点
 *
 * 数据来源：schedulerApi（直接调后端 4 个管理 API）
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { schedulerApi } from '@/lib/modules/scheduler/api';
import type { SchedulerJob, SchedulerJobRun } from '@/lib/modules/scheduler/types';
import { JobCard } from './components/JobCard';

export default function SchedulerPage() {
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null);

  // 任务级状态：每个 job 一把"切换中 / 执行中"锁（防快速连点）
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  // 当前展开历史的任务 id + 各任务已拉取的历史
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

  // 首屏拉一次
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

  // 启停：乐观更新 + 失败回滚
  const handleToggle = async (job: SchedulerJob, nextEnabled: boolean) => {
    if (togglingIds.has(job.id)) return;
    setTogglingIds((s) => new Set(s).add(job.id));
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

  // 立即执行：触发成功后 3 秒延时刷新历史与任务列表（给后端留执行时间）
  const handleRun = async (job: SchedulerJob) => {
    if (runningIds.has(job.id)) return;
    setRunningIds((s) => new Set(s).add(job.id));
    setToast({ kind: 'success', msg: `${job.name} 已触发，几秒后刷新历史` });
    try {
      await schedulerApi.runNow(job.id);
      setTimeout(() => {
        reloadRuns(job.id);
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
    <main className="min-h-screen bg-black text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* 头部：返回主页 + 标题 + 全局刷新 */}
        <header className="mb-8">
          {/* Link href 是 app 内路径，basePath=/macro 自动补全 → 实际跳 /macro/ 主页 */}
          <Link href="/" className="text-gray-400 hover:text-white transition-colors">
            ← 返回宏观主页
          </Link>
          <div className="flex items-center justify-between mt-4">
            <h1 className="text-4xl font-bold">定时任务管理</h1>
            <button
              onClick={reload}
              disabled={loading}
              className="text-sm px-3 py-1.5 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors disabled:opacity-50"
            >
              {loading ? '刷新中…' : '刷新'}
            </button>
          </div>
        </header>

        {toast && (
          <div
            className={`px-4 py-2 rounded text-sm border mb-4 ${
              toast.kind === 'success'
                ? 'bg-green-900/50 border-green-700 text-green-200'
                : 'bg-red-900/50 border-red-700 text-red-200'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="text-xs text-gray-400 bg-gray-900 border border-gray-800 rounded px-3 py-2 mb-4">
          后端内建定时调度：A 股组（收盘后）与全球组（北京早晨）各一个组任务，顺序更新组内全部数据源。
          cron 由配置文件固定，UI 仅开放启用/禁用与立即执行。
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
    </main>
  );
}
