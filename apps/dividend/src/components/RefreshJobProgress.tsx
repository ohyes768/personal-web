import type { RefreshJob } from '@/lib/types';
import { isRefreshActive } from '@/lib/hooks/useRefreshJobs';

export function RefreshJobProgress({ job, error, onRetry }: {
  job?: RefreshJob; error?: string; onRetry: (codes: string[]) => void;
}) {
  if (!job) return error ? <p role="status" className="text-xs text-amber-600">{error}</p> : null;
  const labels = { queued: '等待刷新', running: '刷新中', succeeded: '全部完成', partial_failed: '部分失败', failed: '刷新失败', interrupted: '刷新已中断，可重试' };
  const active = isRefreshActive(job);
  return (
    <div role="status" aria-live="polite" className="my-2 rounded-md border border-rule bg-paper-tint p-2 text-xs text-ink-muted">
      <p className={active ? 'text-info' : job.status === 'succeeded' ? 'text-up' : 'text-amber-600'}>{job.kind === 'm120' ? 'M120 均线' : '财务指标'} · <span>{labels[job.status]}</span></p>
      {active && job.reused && <p>已有同类任务，继续显示当前进度</p>}
      <p>已处理 {job.processed}/{job.total}，成功 {job.succeeded}，失败 {job.failed}，未处理 {job.remaining}</p>
      {active && <progress aria-label={`${job.kind} 刷新进度`} className="mt-1 h-1.5 w-full" value={job.processed} max={Math.max(job.total, 1)} />}
      {(error || job.error) && <p className="mt-1 text-amber-600">{error || job.error}</p>}
      {!active && job.retry_codes.length > 0 && (
        <button type="button" className="mt-1 text-info underline" onClick={() => onRetry(job.retry_codes)}>重试失败和未处理股票</button>
      )}
    </div>
  );
}
