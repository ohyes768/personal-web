/**
 * 统一任务队列弹框：基本面评级 + 挡位估值两类任务合并在一个面板里。
 * 只展示正在分析与排队中的任务；每行带类型徽章，能看出现在跑的是哪类、
 * 其余任务因排在后面而等待。顺序和取消结果以服务端快照为准；关闭弹框只停本地计时。
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal } from './shared-ui/Modal';
import { formatElapsedSince } from '@/lib/quality';

const buttonClass = 'rounded border border-rule-strong px-2 py-1 text-xs text-ink hover:border-accent disabled:opacity-40';

/**
 * 错误摘要：压成一行。
 *
 * 后端原文可能很长（如「run xxx 超过 3600s 未完成（最后状态 running）」），
 * 直接渲染会把弹框撑高；这里只显示摘要，全文留在 title 提示里。
 */
export function summarizeQueueError(error: string | null | undefined, maxLength = 36): string {
  if (!error) return '';
  const flat = error.replace(/\s+/g, ' ').trim();
  if (!flat) return '';
  return flat.length > maxLength ? `${flat.slice(0, maxLength)}…` : flat;
}

/** 队列面板行的最小结构（Quality/Valuation 行都满足） */
export interface QueueRowData {
  code: string;
  itemId: string | null;
  name: string | null;
  state: string;
  error: string | null;
  startedAt: string | null;
  position: number | null;
}

export interface QueuePanelView {
  rows: QueueRowData[];
  runningCount: number;
  queuedCount: number;
}

/** 一类任务在统一队列里的一节：自己的数据源与取消/调序接口 */
export interface TaskQueueSection {
  /** 行首徽章文案（评级 / 估值） */
  label: string;
  view: QueuePanelView;
  onCancel: (itemId: string) => Promise<string>;
  onMove: (itemId: string, action: 'front' | 'up' | 'down') => Promise<string>;
}

export interface TaskQueuePanelProps {
  sections: TaskQueueSection[];
}

export function TaskQueuePanel({ sections }: TaskQueuePanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const busyIds = useRef(new Set<string>());
  const [inflight, setInflight] = useState<ReadonlySet<string>>(new Set());
  const [actionError, setActionError] = useState('');
  const runningCount = useMemo(() => sections.reduce((sum, s) => sum + s.view.runningCount, 0), [sections]);
  const queuedCount = useMemo(() => sections.reduce((sum, s) => sum + s.view.queuedCount, 0), [sections]);
  // 各节的排队计数：排队按钮的「已在队尾」判定按本节位次算
  const queuedCountByLabel = useMemo(
    () => Object.fromEntries(sections.map(s => [s.label, s.view.queuedCount])) as Record<string, number>,
    [sections],
  );
  const active = runningCount > 0;
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
        任务队列
        <span className="text-xs text-ink-muted">运行 {runningCount} · 排队 {queuedCount}</span>
      </button>
      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="任务队列" size="md">
        <div className="rounded-xl border border-rule bg-paper-card p-4">
          <p className="text-xs text-ink-muted">运行 {runningCount} · 排队 {queuedCount}</p>
          {actionError && <p role="alert" className="mt-2 text-xs text-red-700">{actionError}</p>}
          {runningCount === 0 && queuedCount === 0 && (
            <p className="mt-2 text-xs text-ink-muted">暂无进行中的任务</p>
          )}
          {sections.map(section => {
            const running = section.view.rows.filter(row => row.state === 'running' || row.state === 'cancelling');
            const queued = section.view.rows.filter(row => row.state === 'queued');
            if (running.length === 0 && queued.length === 0) return null;
            return (
              <section key={section.label} className="mt-3">
                <h3 className="text-sm font-medium text-ink">{section.label}</h3>
                {running.length > 0 && (
                  <ul className="mt-1 space-y-2">
                    {running.map(row => {
                      const cancelling = row.state === 'cancelling' || inflight.has(row.itemId || '');
                      return (
                        <li key={row.itemId || row.code} className="flex flex-wrap items-center gap-2 text-sm">
                          <TypeBadge label={section.label} state={row.state} />
                          <span className="font-medium text-ink">{row.name || row.code}</span>
                          <span className="text-xs text-ink-muted">{row.code}</span>
                          <span className="text-xs text-ink-muted">已分析 {formatElapsedSince(row.startedAt, nowMs)}</span>
                          <button
                            type="button"
                            className={buttonClass}
                            disabled={!row.itemId || cancelling}
                            onClick={() => row.itemId && void run(row.itemId, () => section.onCancel(row.itemId!))}
                          >
                            {cancelling ? '取消中…' : '取消'}
                          </button>
                          {row.error && (
                            <span
                              className="basis-full truncate text-xs text-red-700"
                              title={row.error}
                            >
                              {summarizeQueueError(row.error)}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {queued.length > 0 && (
                  <ul className="mt-1 space-y-2">
                    {queued.map(row => (
                      <QueueRow
                        key={row.itemId || row.code}
                        row={row}
                        typeLabel={section.label}
                        queuedCount={queuedCountByLabel[section.label] ?? queued.length}
                        busy={inflight.has(row.itemId || '')}
                        onMove={action => row.itemId && void run(row.itemId, () => section.onMove(row.itemId!, action))}
                        onCancel={() => row.itemId && void run(row.itemId, () => section.onCancel(row.itemId!))}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      </Modal>
    </>
  );
}

/** 行首类型徽章：评级 / 估值；运行中的任务补「正在分析」前缀 */
function TypeBadge({ label, state }: { label: string; state: string }) {
  const running = state === 'running' || state === 'cancelling';
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs ${running ? 'bg-paper-deep text-accent-deep font-medium' : 'bg-paper-tint text-ink-muted'}`}
    >
      {running ? `${label}·正在分析` : `${label}·排队`}
    </span>
  );
}

function QueueRow({ row, typeLabel, queuedCount, busy, onMove, onCancel }: {
  row: QueueRowData;
  typeLabel: string;
  queuedCount: number;
  busy: boolean;
  onMove: (action: 'front' | 'up' | 'down') => void;
  onCancel: () => void;
}) {
  const atFront = row.position === 1;
  const atBack = row.position === queuedCount;
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <TypeBadge label={typeLabel} state={row.state} />
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
