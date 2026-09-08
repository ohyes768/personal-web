/**
 * 全量刷新弹窗：预筛选表单 + 4 阶段进度
 *
 * 预筛选维度（min_age / min_size_yi / min_mgr_exp）在弹窗内填，
 * 传给后端 /full/refresh 端点 → 后端 SQL 预过滤 universe。
 * refresh 完成后回调 onComplete(preFilters) 把值同步到左侧筛选面板（disabled）。
 */
'use client';

import { ArrowPathIcon, CheckCircleIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { RefreshStatus } from '@/lib/types';

interface FullRefreshDialogProps {
  open: boolean;
  onClose: () => void;
  /** /api/funds/discovery-{bond,stock}/full/refresh */
  refreshUrl: string;
  /** /api/funds/discovery-{bond,stock}/full/refresh/status */
  statusUrl: string;
  /** refresh 完成后回调（preFilters 同步到左侧筛选面板） */
  onComplete: (preFilters: { min_ret_1y: number | null; min_ret_3y: number | null; max_nav_stale_days: number | null }) => void;
  /** 默认预筛选值（来自上次 refresh） */
  initial?: { min_ret_1y: number | null; min_ret_3y: number | null; max_nav_stale_days: number | null };
}

const POLL_INTERVAL_MS = 2000;

export function FullRefreshDialog({
  open, onClose, refreshUrl, statusUrl, onComplete, initial,
}: FullRefreshDialogProps) {
  // 默认预筛选：L1 业绩字段（min_ret_3y=0 跑全集；用户填大值砍规模）
  const [minRet1y, setMinRet1y] = useState<number | null>(initial?.min_ret_1y ?? null);
  const [minRet3y, setMinRet3y] = useState<number | null>(initial?.min_ret_3y ?? 0);
  const [maxNavStaleDays, setMaxNavStaleDays] = useState<number | null>(initial?.max_nav_stale_days ?? null);
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stoppedRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    stoppedRef.current = true;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  useEffect(() => {
    if (!open) {
      stopPolling();
      setStatus(null);
      setError(null);
      setRefreshing(false);
    }
  }, [open, stopPolling]);

  const pollOnce = useCallback(async (taskId: string) => {
    if (stoppedRef.current) return;
    try {
      const res = await fetch(`${statusUrl}?task_id=${taskId}`, { cache: 'no-store' });
      if (!res.ok) {
        // sub-task（"test_L1_rank"）查不到 → 父 task 的 status（聚合）
        const r = await fetch(`${refreshUrl}/status?task_id=${taskId}`, { cache: 'no-store' });
        if (!r.ok) return;
        const s: RefreshStatus = await r.json();
        if (stoppedRef.current) return;
        setStatus(s);
        if (s.status !== 'running') {
          stopPolling();
          if (s.status === 'done') {
            onComplete({
              min_ret_1y: minRet1y,
              min_ret_3y: minRet3y,
              max_nav_stale_days: maxNavStaleDays,
            });
          }
        }
        return;
      }
      const s: RefreshStatus = await res.json();
      if (stoppedRef.current) return;
      setStatus(s);
      if (s.status !== 'running') {
        stopPolling();
        if (s.status === 'done') {
          onComplete({
            min_ret_1y: minRet1y,
            min_ret_3y: minRet3y,
            max_nav_stale_days: maxNavStaleDays,
          });
        }
      }
    } catch {
      // 轮询失败静默，下轮重试
    }
  }, [statusUrl, refreshUrl, stopPolling, onComplete, minRet1y, minRet3y, maxNavStaleDays]);

  const startRefresh = useCallback(async () => {
    setRefreshing(true);
    setStatus(null);
    setError(null);
    stoppedRef.current = false;

    const params = new URLSearchParams();
    if (minRet1y != null) params.set('min_ret_1y', String(minRet1y));
    if (minRet3y != null) params.set('min_ret_3y', String(minRet3y));
    if (maxNavStaleDays != null) params.set('max_nav_stale_days', String(maxNavStaleDays));
    const q = params.toString();
    const url = q ? `${refreshUrl}?${q}` : refreshUrl;

    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const r: { task_id: string; status: string } = await res.json();
      // 立即轮询一次（不等 interval）
      timerRef.current = setInterval(() => pollOnce(r.task_id), POLL_INTERVAL_MS);
      pollOnce(r.task_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '触发失败');
      setRefreshing(false);
    }
  }, [refreshUrl, minRet1y, minRet3y, maxNavStaleDays, pollOnce]);

  if (!open) return null;

  const pct = status && status.total > 0
    ? Math.round(((status.completed + status.failed) / status.total) * 100)
    : 0;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="fixed right-3 top-16 z-50 w-80 bg-paper-card border border-rule rounded-lg shadow-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-ink-strong">全量刷新</span>
          <button
            onClick={onClose}
            className="p-1 text-ink-muted hover:text-ink-strong"
            aria-label="关闭"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>

        {!refreshing && !status && (
          <>
            <p className="text-xs text-ink-muted mb-3">
              预筛选（缩小拉取范围；拉到约 600 只约 10 分钟，不筛约 1.5 小时跑全 4000+ 只）
            </p>
            <div className="space-y-2 mb-3">
              <p className="text-[10px] text-ink-soft mb-1.5">
                业绩预筛选（用 L1 market_fund_rank 字段；L2 字段 99% NULL 做预筛会砍到 0 不可用）
              </p>
              <NumberField label="近 1 年涨 ≥" value={minRet1y} onChange={setMinRet1y} placeholder="不限" unit="%" />
              <NumberField label="近 3 年涨 ≥" value={minRet3y} onChange={setMinRet3y} placeholder="不限" unit="%" />
              <NumberField label="净值新鲜度 ≤" value={maxNavStaleDays} onChange={setMaxNavStaleDays} placeholder="不限" unit="天" />
            </div>
            {error && <p className="text-xs text-down mb-2">{error}</p>}
            <button
              onClick={startRefresh}
              disabled={refreshing}
              className="w-full px-3 py-2 text-sm text-white bg-accent hover:bg-accent-hover disabled:opacity-50 rounded transition-colors"
            >
              {refreshing ? '启动中…' : '开始全量刷新'}
            </button>
          </>
        )}

        {refreshing && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-muted flex items-center gap-1">
                <ArrowPathIcon className={`w-4 h-4 ${status?.status === 'running' ? 'animate-spin' : ''}`} />
                {status?.status === 'done' ? '完成' : status?.status === 'error' ? '出错' : '进行中'}
                {status && `：${status.completed}/${status.total}`}
              </span>
              {status && status.failed > 0 && <span className="text-down">失败 {status.failed}</span>}
            </div>
            <div className="h-1.5 bg-paper-deep rounded-full overflow-hidden">
              <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-[11px] text-ink-soft mt-2">
              4 阶段流水线：业绩 → 经理/类型 → 净值 → 风险指标
            </p>
            {status?.status === 'done' && (
              <div className="flex items-center gap-1 text-xs text-up mt-2">
                <CheckCircleIcon className="w-4 h-4" />
                已完成，筛选面板已同步预筛选值
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function NumberField({ label, value, onChange, placeholder, unit }: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder: string;
  unit?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-ink-strong shrink-0">{label}</span>
      <div className="flex items-center gap-1">
        <input
          type="number"
          min={0}
          value={value ?? ''}
          placeholder={placeholder}
          onChange={e => {
            const raw = e.target.value;
            onChange(raw === '' ? null : Number(raw));
          }}
          className="w-16 px-1.5 py-1 text-right tnum border border-rule rounded bg-paper-card focus:outline-none focus:border-info"
        />
        {unit && <span className="text-[10px] text-ink-soft">{unit}</span>}
      </div>
    </div>
  );
}
