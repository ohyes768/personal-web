'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowPathIcon, PlayIcon } from '@heroicons/react/24/outline';
import { schedulerApi, type CollectionResult, type RunStatus, type SchedulerJob, type SchedulerRun } from '@/lib/scheduler';

const TABS = [
  ['bond', '债基·雪球三分法'], ['stock', '股基·雪球三分法'],
  ['discovery-bond', '债基·市场'], ['discovery-stock', '股基·市场'],
] as const;
const STATUS: Record<RunStatus, { label: string; color: string }> = {
  running: { label: '运行中', color: 'text-info' },
  success: { label: '成功', color: 'text-up' },
  partial: { label: '部分成功', color: 'text-accent' },
  failed: { label: '失败', color: 'text-down' },
};
const button = 'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md border border-rule-strong px-3 text-sm text-ink hover:bg-paper-deep disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-info';

function time(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(value));
}
function duration(run: { start: string; end?: string }) {
  if (!run.end) return '进行中';
  const seconds = Math.round((Date.parse(run.end) - Date.parse(run.start)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}
function Status({ value }: { value: RunStatus }) {
  const status = STATUS[value] ?? { label: '未知状态', color: 'text-ink-muted' };
  return <span className={`text-sm font-medium ${status.color}`}>{status.label}</span>;
}
function errors(result?: CollectionResult): string[] {
  if (!result) return [];
  return [...(result.errors ?? []), ...Object.values(result.stage_results ?? {}).flatMap(stage => [
    ...(stage.error ? [stage.error] : []), ...errors(stage.result),
  ])];
}

function RunDetails({ run, current = false }: { run: SchedulerRun; current?: boolean }) {
  return <div className="mt-3 border-t border-rule">
    {TABS.map(([tab, label]) => {
      const item = run.items.find(entry => entry.tab === tab);
      const messages = [...(item?.error ? [item.error] : []), ...errors(item?.result)];
      return <div key={tab} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 border-b border-rule py-3 text-sm sm:grid-cols-[minmax(0,1fr)_7rem_10rem]">
        <div className="min-w-0"><span className="text-ink-strong">{label}</span>
          {messages.length > 0 && <p className="mt-1 break-words text-xs text-down">{messages.slice(0, 3).join('；')}{messages.length > 3 ? `（另 ${messages.length - 3} 条）` : ''}</p>}
        </div>
        <span>{item ? <Status value={item.status} /> : <span className="text-ink-muted">{current ? '等待执行' : '无明细'}</span>}</span>
        <span className="col-span-2 text-xs text-ink-muted sm:col-span-1 sm:text-right">{item ? `${time(item.start)} · ${duration(item)}` : '—'}</span>
      </div>;
    })}
    {run.error && <p role="alert" className="mt-3 break-words text-sm text-down">{run.error}</p>}
  </div>;
}

export default function SchedulerPage() {
  const [job, setJob] = useState<SchedulerJob | null>(null);
  const [runs, setRuns] = useState<SchedulerRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState<'toggle' | 'run' | null>(null);
  const mounted = useRef(false);
  const fetching = useRef(false);
  const mutating = useRef(false);
  const revision = useRef(0);
  const retryAction = useRef<'toggle' | 'run'>('toggle');

  const reload = useCallback(async () => {
    if (fetching.current || mutating.current) return;
    fetching.current = true;
    const requestedRevision = revision.current;
    try {
      const { jobs } = await schedulerApi.jobs();
      if (!mounted.current || requestedRevision !== revision.current) return;
      const next = jobs[0] ?? null;
      setJob(next);
      setError('');
      if (next) {
        try {
          const history = await schedulerApi.runs(next.id);
          if (mounted.current && requestedRevision === revision.current) { setRuns(history.runs); setHistoryError(''); }
        } catch (exception) {
          if (mounted.current) setHistoryError(exception instanceof Error ? exception.message : '历史加载失败，请重试');
        }
      }
    } catch (exception) {
      if (mounted.current && requestedRevision === revision.current) setError(exception instanceof Error ? exception.message : '加载失败，请重试');
    } finally {
      fetching.current = false;
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void reload();
    const timer = setInterval(() => { if (!document.hidden) void reload(); }, 5000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [reload]);

  async function act(action: 'toggle' | 'run') {
    if (!job || mutating.current || (action === 'run' && job.running)) return;
    mutating.current = true;
    revision.current += 1;
    retryAction.current = action;
    setBusy(action); setNotice(''); setActionError('');
    try {
      if (action === 'toggle') {
        const updated = await schedulerApi.setEnabled(job.id, !job.enabled);
        if (mounted.current) {
          setJob(updated);
          setNotice(updated.enabled ? '自动更新已启用' : '自动更新已暂停；已开始的任务会继续完成');
        }
      } else {
        await schedulerApi.run(job.id);
        if (mounted.current) {
          setJob(previous => previous ? { ...previous, running: true } : previous);
          setNotice('刷新已启动，四个 tab 将依次更新');
        }
      }
      if (mounted.current) setError('');
    } catch (exception) {
      if (mounted.current) setActionError(exception instanceof Error ? exception.message : '操作失败，请重试');
    } finally {
      mutating.current = false;
      if (mounted.current) { setBusy(null); void reload(); }
    }
  }

  return <main className="mx-auto min-h-screen max-w-5xl px-4 py-6 sm:px-8 sm:py-10">
    <header>
      <Link href="/bond" className="text-sm text-ink-muted underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-info">← 返回基金筛选</Link>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-ink-strong sm:text-3xl">定时任务</h1>
        <button className={button} onClick={() => void reload()} disabled={loading || busy !== null}>
          <ArrowPathIcon aria-hidden="true" className="h-4 w-4" />刷新状态
        </button>
      </div>
      <p className="mt-3 text-sm leading-6 text-ink-muted">每周更新四个基金 tab。所有时间均为北京时间，任务按顺序执行。</p>
    </header>
    {(error || actionError) && <div role="alert" className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-rule bg-down-tint p-3 text-sm text-down">{actionError || error}<button className={button} disabled={busy !== null} onClick={() => { if (actionError) void act(retryAction.current); else void reload(); }}>重试</button></div>}
    {notice && <p role="status" className="mt-5 text-sm text-info">{notice}</p>}
    {loading && !job ? <p role="status" className="py-12 text-sm text-ink-muted">正在加载定时任务…</p> : job ? <>
      <section aria-labelledby="weekly-heading" className="mt-8 border-y border-rule py-6">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <h2 id="weekly-heading" className="text-lg font-semibold text-ink-strong">四个基金 tab 每周更新</h2>
            <p className="mt-2 text-sm text-ink-muted">{job.cron_human} · {job.enabled ? '自动更新已启用' : '自动更新已暂停'}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button role="switch" aria-label="每周自动更新" aria-checked={job.enabled} className={button} disabled={busy !== null} onClick={() => void act('toggle')}>
              {busy === 'toggle' ? '保存中…' : job.enabled ? '暂停自动更新' : '启用自动更新'}
            </button>
            <button className={`${button} border-accent bg-accent text-white hover:bg-accent-hover`} disabled={busy !== null || job.running} onClick={() => void act('run')}>
              <PlayIcon aria-hidden="true" className="h-4 w-4" />{job.running ? '正在执行' : busy === 'run' ? '启动中…' : '立即执行'}
            </button>
          </div>
        </div>
        <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
          <div><dt className="text-ink-muted">下次自动执行</dt><dd className="mt-1.5 tnum text-ink-strong">{job.enabled ? time(job.next_run_time) : '已暂停'}</dd></div>
          <div><dt className="text-ink-muted">上次执行</dt><dd className="mt-1.5 tnum text-ink-strong">{job.last_run ? time(job.last_run.start) : '尚未执行'}</dd></div>
          <div><dt className="text-ink-muted">当前状态</dt><dd className="mt-1.5">{job.running ? <Status value="running" /> : job.last_run ? <Status value={job.last_run.status} /> : '等待首次执行'}</dd></div>
        </dl>
        <p className="mt-6 max-w-2xl text-xs leading-6 text-ink-muted">刷新顺序：债基·雪球三分法 → 股基·雪球三分法 → 债基·市场 → 股基·市场。市场预筛选沿用默认值：债基近三年收益 ≥10%，股基 ≥20%；规模均 ≥5 亿，经理从业均 ≥5 年。</p>
        {job.running && job.current_run && <div className="mt-6" aria-live="polite"><h3 className="text-sm font-semibold text-ink-strong">本轮执行进度</h3><RunDetails run={job.current_run} current /></div>}
        {!job.running && job.last_run?.error && <p className="mt-4 break-words text-sm text-down">{job.last_run.error}</p>}
      </section>
      <section aria-labelledby="history-heading" className="mt-8 pb-10">
        <div className="flex items-baseline justify-between gap-3"><h2 id="history-heading" className="text-lg font-semibold text-ink-strong">执行历史</h2><span className="text-xs text-ink-muted">最近 20 次 · 每 5 秒更新</span></div>
        {historyError && <p role="alert" className="mt-4 text-sm text-down">{historyError} <button className="underline underline-offset-4" onClick={() => void reload()}>重新加载历史</button></p>}
        {!historyError && runs.length === 0 && <p className="mt-4 text-sm leading-6 text-ink-muted">暂无执行记录。可等待下次自动更新，或点击“立即执行”；本轮完成后会显示四个 tab 的结果。</p>}
        <div className="mt-4 divide-y divide-rule">
          {runs.map((run, index) => <details key={run.run_id ?? `${run.start}-${index}`} className="group py-4">
            <summary className="cursor-pointer rounded-sm text-sm focus-visible:outline-2 focus-visible:outline-info">
              <span className="ml-1 inline-flex flex-wrap items-center gap-x-5 gap-y-2 align-middle">
                <span className="tnum text-ink-strong">{time(run.start)}</span><Status value={run.status} />
                <span className="text-ink-muted">{run.trigger === 'manual' ? '手动执行' : '定时执行'} · {duration(run)}</span>
                <span className="text-xs text-info">查看四项结果</span>
              </span>
            </summary>
            <RunDetails run={run} />
          </details>)}
        </div>
      </section>
    </> : !error && <p className="py-12 text-sm text-ink-muted">暂无已配置的定时任务。</p>}
  </main>;
}
