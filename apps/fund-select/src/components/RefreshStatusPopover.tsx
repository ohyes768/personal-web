/**
 * 刷新状态弹窗：触发刷新 + 轮询进度
 */
'use client';

import { ArrowPathIcon, CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline';
import { useEffect, useRef, useState } from 'react';

import { fundApi } from '@/lib/api';
import type { RefreshStatus } from '@/lib/types';

interface RefreshStatusPopoverProps {
  onRefreshed?: () => void;
  /** 覆盖默认刷新端点（不传走 fundApi.refresh）。股票 tab 传 '/funds/api/funds/stock/refresh' */
  refreshUrl?: string;
  /** 覆盖默认状态端点。股票 tab 传 '/funds/api/funds/stock/refresh/status' */
  statusUrl?: string;
}

const POLL_INTERVAL_MS = 5000;

export function RefreshStatusPopover({ onRefreshed, refreshUrl, statusUrl }: RefreshStatusPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => stopPolling, []);

  const startRefresh = async () => {
    setStarting(true);
    setStatus(null);
    try {
      let r;
      if (refreshUrl) {
        const res = await fetch(refreshUrl, { cache: 'no-store' });
        r = await res.json();
      } else {
        r = await fundApi.refresh();
      }
      stopPolling();
      timerRef.current = setInterval(async () => {
        try {
          let s: RefreshStatus;
          if (statusUrl) {
            const res = await fetch(`${statusUrl}?task_id=${r.task_id}`, { cache: 'no-store' });
            s = await res.json();
          } else {
            s = await fundApi.getRefreshStatus(r.task_id);
          }
          setStatus(s);
          if (s.status !== 'running') {
            stopPolling();
            onRefreshed?.();
          }
        } catch {
          // 轮询失败静默，下轮重试
        }
      }, POLL_INTERVAL_MS);
    } catch (e) {
      setStatus({
        task_id: '', status: 'error', total: 0, completed: 0, failed: 0,
        errors: [e instanceof Error ? e.message : '触发失败'],
      });
    } finally {
      setStarting(false);
    }
  };

  const running = status?.status === 'running';
  const pct = status && status.total > 0
    ? Math.round(((status.completed + status.failed) / status.total) * 100)
    : 0;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(o => !o)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
        aria-label="刷新数据"
        aria-expanded={isOpen}
      >
        <ArrowPathIcon className={`w-4 h-4 ${running ? 'animate-spin' : ''}`} />
        刷新
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} aria-hidden="true" />
          <div className="absolute right-0 top-full mt-2 z-50 w-72 bg-paper-card border border-rule rounded-lg shadow-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-ink-strong">数据刷新</span>
              <button
                onClick={startRefresh}
                disabled={starting || running}
                className="px-2.5 py-1 text-xs text-white bg-accent hover:bg-accent-hover disabled:opacity-50 rounded transition-colors"
              >
                {running ? '刷新中…' : starting ? '启动中…' : '立即刷新'}
              </button>
            </div>

            {!status && (
              <p className="text-xs text-ink-muted">
                拉取配置名单 31 只基金（净值 / 季报持仓 / 费率），约 2-3 分钟
              </p>
            )}

            {status && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-muted">
                    {status.status === 'running' ? '进行中' : status.status === 'done' ? '完成' : '出错'}
                    ：{status.completed}/{status.total}
                  </span>
                  {status.failed > 0 && (
                    <span className="text-down">失败 {status.failed}</span>
                  )}
                </div>
                <div className="h-1.5 bg-paper-deep rounded-full overflow-hidden">
                  <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
                </div>
                {status.status === 'done' && (
                  <div className="flex items-center gap-1 text-xs text-up">
                    <CheckCircleIcon className="w-4 h-4" />
                    已完成，数据已更新
                  </div>
                )}
                {status.errors.length > 0 && (
                  <div className="max-h-24 overflow-y-auto text-[11px] text-down space-y-0.5">
                    {status.errors.slice(0, 5).map((e, i) => (
                      <div key={i} className="flex items-start gap-1">
                        <ExclamationCircleIcon className="w-3 h-3 mt-0.5 shrink-0" />
                        <span className="break-all">{e}</span>
                      </div>
                    ))}
                    {status.errors.length > 5 && <span>…共 {status.errors.length} 条</span>}
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
