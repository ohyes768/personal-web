'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowPathIcon, PlayIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { schedulerApi, type CollectionResult, type RunStatus, type SchedulerJob, type SchedulerRun } from '@/lib/scheduler';

const STATUS: Record<RunStatus, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'text-info' },
  running: { label: '运行中', color: 'text-info' },
  success: { label: '成功', color: 'text-up' },
  partial: { label: '部分成功', color: 'text-accent' },
  failed: { label: '失败', color: 'text-down' },
};
const button = 'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md border border-rule-strong px-3 text-sm text-ink hover:bg-paper-deep disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-info';

function time(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}
function duration(run: SchedulerRun) {
  if (!run.end) return run.status === 'queued' ? '等待上一项完成' : '进行中';
  const seconds = Math.round((Date.parse(run.end) - Date.parse(run.start)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}
function Status({ value }: { value: RunStatus }) {
  const status = STATUS[value] ?? { label: '未知状态', color: 'text-ink-muted' };
  return <span className={`font-medium ${status.color}`}>{status.label}</span>;
}
function errors(result?: CollectionResult): string[] {
  if (!result) return [];
  return [...(result.errors ?? []), ...Object.values(result.stage_results ?? {}).flatMap(stage => [
    ...(stage.error ? [stage.error] : []), ...errors(stage.result),
  ])];
}
function RunErrors({ run }: { run: SchedulerRun }) {
  const messages = [...(run.error ? [run.error] : []), ...run.items.flatMap(item => [
    ...(item.error ? [item.error] : []), ...errors(item.result),
  ])];
  return messages.length > 0 ? <p className="mt-2 break-words text-xs leading-5 text-down">{messages.slice(0, 3).join('；')}{messages.length > 3 ? `（另 ${messages.length - 3} 条）` : ''}</p> : null;
}

export function SchedulerDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const mounted = useRef(false);
  const version = useRef(0);
  const mutation = useRef(false);
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [runs, setRuns] = useState<Record<string, SchedulerRun[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState<{ id: string; action: 'toggle' | 'run' } | null>(null);

  useEffect(() => {
    mounted.current = true;
    const element = dialog.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    closeButton.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      mounted.current = false;
      element?.close();
      document.body.style.overflow = overflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    let active = true;
    let fetching = false;
    const controller = new AbortController();
    setHistoryError('');
    async function reload() {
      if (fetching || mutation.current) return;
      fetching = true;
      const requestedVersion = version.current;
      try {
        const response = await schedulerApi.jobs(controller.signal);
        if (!active || requestedVersion !== version.current) return;
        setJobs(response.jobs); setLoadError('');
        if (expanded) {
          try {
            const history = await schedulerApi.runs(expanded, controller.signal);
            if (active && requestedVersion === version.current) {
              setRuns(previous => ({ ...previous, [expanded!]: history.runs }));
              setHistoryError('');
            }
          } catch (error) {
            if (active && requestedVersion === version.current) setHistoryError(error instanceof Error ? error.message : '历史加载失败，请重试');
          }
        }
      } catch (error) {
        if (active && requestedVersion === version.current) setLoadError(error instanceof Error ? error.message : '任务加载失败，请重试');
      } finally {
        fetching = false;
        if (active) setLoading(false);
      }
    }
    void reload();
    const timer = setInterval(() => { if (!document.hidden) void reload(); }, 5000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [expanded, revision]);

  async function act(job: SchedulerJob, action: 'toggle' | 'run') {
    if (mutation.current || (action === 'run' && job.running)) return;
    mutation.current = true; version.current += 1;
    setBusy({ id: job.id, action }); setActionError(''); setNotice('');
    try {
      if (action === 'toggle') {
        const updated = await schedulerApi.setEnabled(job.id, !job.enabled);
        if (mounted.current) {
          setJobs(previous => previous.map(entry => entry.id === job.id ? updated : entry));
          setNotice(`${job.name}：自动更新已${updated.enabled ? '启用' : '暂停'}`);
        }
      } else {
        await schedulerApi.run(job.id);
        if (mounted.current) {
          setJobs(previous => previous.map(entry => entry.id === job.id ? { ...entry, running: true } : entry));
          setNotice(`${job.name}：已提交执行，采集繁忙时会自动排队`);
        }
      }
    } catch (error) {
      if (mounted.current) setActionError(`${job.name}：${error instanceof Error ? error.message : '操作失败，请重试'}`);
    } finally {
      mutation.current = false;
      if (mounted.current) { setBusy(null); setRevision(value => value + 1); }
    }
  }

  return <dialog ref={dialog} aria-labelledby="scheduler-title" onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}
    style={{ margin: 'auto', width: 'calc(100% - 2rem)' }}
    className="max-h-[90dvh] max-w-4xl overflow-hidden rounded-xl border border-rule bg-paper-card p-0 text-ink shadow-xl backdrop:bg-black/40">
    <div className="flex max-h-[90dvh] flex-col">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-rule px-4 py-4 sm:px-6">
        <div><h2 id="scheduler-title" className="text-xl font-semibold text-ink-strong">定时任务</h2><p className="mt-1.5 text-xs leading-5 text-ink-muted">每周六错峰更新 · 北京时间 · 四项独立管理</p></div>
        <div className="flex shrink-0 gap-1">
          <button type="button" className={button} disabled={loading || busy !== null} onClick={() => setRevision(value => value + 1)} aria-label="刷新任务状态"><ArrowPathIcon aria-hidden="true" className="h-4 w-4" /><span className="hidden sm:inline">刷新状态</span></button>
          <button ref={closeButton} type="button" className={`${button} border-transparent px-2`} aria-label="关闭定时任务" onClick={onClose}><XMarkIcon aria-hidden="true" className="h-5 w-5" /></button>
        </div>
      </header>
      <div className="min-h-0 overflow-y-auto overscroll-contain px-4 pb-3 sm:px-6">
        <p className="py-3 text-xs leading-5 text-ink-muted">每项只刷新对应 tab。上一项未完成时，后续任务会排队；暂停自动更新不会中断已提交的任务。</p>
        {loadError && <div role="alert" className="mb-3 flex items-center justify-between gap-3 rounded-md bg-down-tint p-3 text-sm text-down">{loadError}<button className={button} onClick={() => setRevision(value => value + 1)}>重试</button></div>}
        {actionError && <p role="alert" className="mb-3 rounded-md bg-down-tint p-3 text-sm text-down">{actionError}</p>}
        {notice && <p role="status" className="mb-3 text-sm text-info">{notice}</p>}
        {loading && jobs.length === 0 && <p role="status" className="py-10 text-sm text-ink-muted">正在加载定时任务…</p>}
        {!loading && !loadError && jobs.length === 0 && <p className="py-10 text-sm text-ink-muted">暂无已配置的定时任务。</p>}
        {jobs.map(job => <section key={job.id} aria-label={job.name} className="border-t border-rule py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 className="font-semibold text-ink-strong">{job.name}</h3><p className="mt-1 text-sm text-ink-muted">{job.cron_human} · {job.enabled ? '已启用' : '已暂停'}</p></div>
            <div className="flex flex-wrap gap-2">
              <button role="switch" aria-label={`${job.name}自动更新`} aria-checked={job.enabled} disabled={busy !== null} className={button} onClick={() => void act(job, 'toggle')}>{busy?.id === job.id && busy.action === 'toggle' ? '保存中…' : job.enabled ? '暂停' : '启用'}</button>
              <button aria-label={`立即执行${job.name}`} disabled={busy !== null || job.running} className={button} onClick={() => void act(job, 'run')}><PlayIcon aria-hidden="true" className="h-4 w-4" />{job.running ? job.current_run?.status === 'queued' ? '排队中' : '正在执行' : busy?.id === job.id && busy.action === 'run' ? '启动中…' : '立即执行'}</button>
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs sm:grid-cols-3">
            <div><dt className="text-ink-muted">下次自动执行</dt><dd className="mt-1 tnum">{job.enabled ? time(job.next_run_time) : '已暂停'}</dd></div>
            <div><dt className="text-ink-muted">上次执行</dt><dd className="mt-1 tnum">{job.last_run ? time(job.last_run.start) : '尚未执行'}</dd></div>
            <div><dt className="text-ink-muted">当前状态</dt><dd className="mt-1">{job.running ? <Status value={job.current_run?.status ?? 'queued'} /> : job.last_run ? <Status value={job.last_run.status} /> : '等待首次执行'}</dd></div>
          </dl>
          <p className="mt-3 text-xs leading-5 text-ink-muted">{job.description}</p>
          {job.last_run?.error && !job.running && <RunErrors run={job.last_run} />}
          <button type="button" aria-expanded={expanded === job.id} aria-controls={`history-${job.id}`} onClick={() => setExpanded(previous => previous === job.id ? null : job.id)} className="mt-3 min-h-8 rounded text-xs text-info underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-info">{expanded === job.id ? '收起执行历史' : '查看执行历史'}</button>
          {expanded === job.id && <div id={`history-${job.id}`} className="mt-2 border-t border-rule pt-3">
            {historyError && <p role="alert" className="text-xs text-down">{historyError} <button className="underline underline-offset-4" onClick={() => setRevision(value => value + 1)}>重试</button></p>}
            {!runs[job.id] && !historyError && <p role="status" className="text-xs text-ink-muted">正在加载历史…</p>}
            {runs[job.id]?.length === 0 && <p className="text-xs leading-5 text-ink-muted">暂无执行记录，可等待自动更新或点击“立即执行”。</p>}
            <div className="divide-y divide-rule">{runs[job.id]?.map((run, index) => <div key={run.run_id ?? `${run.start}-${index}`} className="py-2 text-xs">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1"><span className="tnum">{time(run.start)}</span><Status value={run.status} /><span className="text-ink-muted">{run.trigger === 'manual' ? '手动执行' : '定时执行'} · {duration(run)}</span></div><RunErrors run={run} />
            </div>)}</div>
            <p className="mt-2 text-xs text-ink-muted">最近 20 次 · 每 5 秒更新</p>
          </div>}
        </section>)}
      </div>
    </div>
  </dialog>;
}
