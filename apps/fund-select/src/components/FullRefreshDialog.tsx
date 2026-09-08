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
  onComplete: (preFilters: { min_age: number | null; min_size_yi: number | null; min_mgr_exp: number | null }) => void;
  /** 默认预筛选值（来自上次 refresh） */
  initial?: { min_age: number | null; min_size_yi: number | null; min_mgr_exp: number | null };
}

const POLL_INTERVAL_MS = 2000;

export function FullRefreshDialog({
  open, onClose, refreshUrl, statusUrl, onComplete, initial,
}: FullRefreshDialogProps) {
  // 默认预筛选：成立 ≥ 3 年 + 规模 ≥ 5 亿（用户希望保持这个初筛）
  const [minAge, setMinAge] = useState<number | null>(initial?.min_age ?? 3);
  const [minSizeYi, setMinSizeYi] = useState<number | null>(initial?.min_size_yi ?? 5);
  const [minMgrExp, setMinMgrExp] = useState<number | null>(initial?.min_mgr_exp ?? null);
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
              min_age: minAge,
              min_size_yi: minSizeYi,
              min_mgr_exp: minMgrExp,
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
            min_age: minAge,
            min_size_yi: minSizeYi,
            min_mgr_exp: minMgrExp,
          });
        }
      }
    } catch {
      // 轮询失败静默，下轮重试
    }
  }, [statusUrl, refreshUrl, stopPolling, onComplete, minAge, minSizeYi, minMgrExp]);

  const startRefresh = useCallback(async () => {
    setRefreshing(true);
    setStatus(null);
    setError(null);
    stoppedRef.current = false;

    const params = new URLSearchParams();
    if (minAge != null) params.set('min_age', String(minAge));
    if (minSizeYi != null) params.set('min_size_yi', String(minSizeYi));
    if (minMgrExp != null) params.set('min_mgr_exp', String(minMgrExp));
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
  }, [refreshUrl, minAge, minSizeYi, minMgrExp, pollOnce]);

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
              <NumberField label="成立年限 ≥" value={minAge} onChange={setMinAge} placeholder="不限" unit="年" />
              <NumberField label="规模 ≥" value={minSizeYi} onChange={setMinSizeYi} placeholder="不限" unit="亿" />
              <NumberField label="经理从业 ≥" value={minMgrExp} onChange={setMinMgrExp} placeholder="不限" unit="年" />
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
