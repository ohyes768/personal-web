/**
 * 评级队列弹框：只展示正在分析与排队中的任务。
 * 顺序和取消结果以服务端快照为准；关闭弹框只停本地计时。
 */
'use client';

import { useEffect, useRef, useState } from 'react';
import { Modal } from './shared-ui/Modal';
import {
  formatElapsedSince,
  type QualityMoveAction,
  type QualityQueueRow,
  type QualityQueueView,
} from '@/lib/quality';

const buttonClass = 'rounded border border-rule-strong px-2 py-1 text-xs text-ink hover:border-accent disabled:opacity-40';

export interface QualityQueuePanelProps {
  view: QualityQueueView;
  onCancel: (itemId: string) => Promise<string>;
  onMove: (itemId: string, action: QualityMoveAction) => Promise<string>;
}

export function QualityQueuePanel({ view, onCancel, onMove }: QualityQueuePanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const busyIds = useRef(new Set<string>());
  const [inflight, setInflight] = useState<ReadonlySet<string>>(new Set());
  const [actionError, setActionError] = useState('');
  const running = view.rows.filter(row => row.state === 'running' || row.state === 'cancelling');
  const queued = view.rows.filter(row => row.state === 'queued');
  const active = running.length > 0;
  useEffect(() => {
    if (!active || !isOpen) return;
    setNowMs(Date.now());
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, isOpen]);

  function markBusy(itemId: string, busy: boolean) {
    if (busy) busyIds.current.add(itemId);
    else busyIds.current.delete(itemId);
    setInflight(new Set(busyIds.current));
  }

  async function run(itemId: string, work: () => Promise<string>) {
    if (!itemId || busyIds.current.has(itemId)) return;
    markBusy(itemId, true);
    setActionError('');
    try {
      const message = await work();
      if (message) setActionError(message);
    } finally {
      markBusy(itemId, false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40 inline-flex flex-wrap items-center gap-x-2"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        评级队列
        <span className="text-xs text-ink-muted">运行 {view.runningCount} · 排队 {view.queuedCount}</span>
      </button>
      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="评级任务队列" size="md">
        <div role="dialog" aria-modal="true" aria-label="评级任务队列" className="rounded-xl border border-rule bg-paper-card p-4">
          <p className="text-xs text-ink-muted">运行 {view.runningCount} · 排队 {view.queuedCount}</p>
          {actionError && <p role="alert" className="mt-2 text-xs text-red-700">{actionError}</p>}
          {running.length === 0 && queued.length === 0 && (
            <p className="mt-2 text-xs text-ink-muted">暂无进行中的任务</p>
          )}
          {running.length > 0 && (
            <section className="mt-3">
              <h3 className="text-sm font-medium text-ink">正在分析</h3>
              <ul className="mt-1 space-y-2">
                {running.map(row => {
                  const cancelling = row.state === 'cancelling' || inflight.has(row.itemId || '');
                  return (
                    <li key={row.itemId || row.code} className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium text-ink">{row.name || row.code}</span>
                      <span className="text-xs text-ink-muted">{row.code}</span>
                      <span className="text-xs text-ink-muted">已分析 {formatElapsedSince(row.startedAt, nowMs)}</span>
                      <button
                        type="button"
                        className={buttonClass}
                        disabled={!row.itemId || cancelling}
                        onClick={() => row.itemId && void run(row.itemId, () => onCancel(row.itemId!))}
                      >
                        {cancelling ? '取消中…' : '取消'}
                      </button>
                      {row.error && <span className="basis-full text-xs text-red-700">{row.error}</span>}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
          {queued.length > 0 && (
            <section className="mt-3">
              <h3 className="text-sm font-medium text-ink">排队中</h3>
              <ul className="mt-1 space-y-2">
                {queued.map(row => (
                  <QueueRow
                    key={row.itemId || row.code}
                    row={row}
                    queuedCount={queued.length}
                    busy={inflight.has(row.itemId || '')}
                    onMove={action => row.itemId && void run(row.itemId, () => onMove(row.itemId!, action))}
                    onCancel={() => row.itemId && void run(row.itemId, () => onCancel(row.itemId!))}
                  />
                ))}
              </ul>
            </section>
          )}
        </div>
      </Modal>
    </>
  );
}

function QueueRow({ row, queuedCount, busy, onMove, onCancel }: {
  row: QualityQueueRow;
  queuedCount: number;
  busy: boolean;
  onMove: (action: QualityMoveAction) => void;
  onCancel: () => void;
}) {
  const atFront = row.position === 1;
  const atBack = row.position === queuedCount;
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <span className="font-medium text-ink">{row.name || row.code}</span>
      <span className="text-xs text-ink-muted">{row.code}</span>
      <span className="text-xs text-ink-muted">第 {row.position ?? '—'} 位</span>
      <button type="button" className={buttonClass} disabled={!row.itemId || atFront || busy} onClick={() => onMove('front')}>置顶</button>
      <button type="button" className={buttonClass} disabled={!row.itemId || atFront || busy} onClick={() => onMove('up')}>上移</button>
      <button type="button" className={buttonClass} disabled={!row.itemId || atBack || busy} onClick={() => onMove('down')}>下移</button>
      <button type="button" className={buttonClass} disabled={!row.itemId || busy} onClick={onCancel}>取消</button>
    </li>
  );
}
