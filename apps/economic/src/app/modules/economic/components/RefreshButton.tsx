'use client';

/**
 * 数据更新按钮
 * - monthly cadence: 更新后置灰到下个月 1 号 00:00（按钮文字显示"下次更新 YYYY-MM"）
 * - daily cadence: 更新后置灰到明天 00:00
 * - 通过 localStorage 持久化 lastUpdatedAt，刷新页面后保持置灰状态
 */
import { useState, useEffect, useCallback } from 'react';
import type { UpdateResponse } from '@/lib/modules/economic/api';

export type RefreshCadence = 'monthly' | 'daily';

interface RefreshButtonProps {
  onRefresh: () => Promise<UpdateResponse>;
  storageKey: string;
  cadence: RefreshCadence;
  label: string;
  onSuccess?: () => void;
}

/** 计算下个 cadence 边界（用用户本地时间，对用户最直观） */
function nextAvailableAt(now: Date, cadence: RefreshCadence): Date {
  const next = new Date(now);
  if (cadence === 'monthly') {
    // 下个月 1 号 00:00 本地时间
    next.setMonth(next.getMonth() + 1, 1);
    next.setHours(0, 0, 0, 0);
  } else {
    // 明天 00:00 本地时间
    next.setDate(next.getDate() + 1);
    next.setHours(0, 0, 0, 0);
  }
  return next;
}

/** 把 Date 格式化为 "YYYY-MM" 或 "YYYY-MM-DD"（按 cadence 区分，用本地时间） */
function formatDateForCadence(d: Date, cadence: RefreshCadence): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  if (cadence === 'monthly') {
    return `${yyyy}-${mm}`;
  }
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function RefreshButton({ onRefresh, storageKey, cadence, label, onSuccess }: RefreshButtonProps) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 每分钟 tick 一次，让"下个月 1 号 00:00 到点后自动恢复可点"
  const [now, setNow] = useState(() => new Date());

  // 首次挂载读 localStorage
  useEffect(() => {
    try {
      setLastUpdatedAt(localStorage.getItem(storageKey));
    } catch {
      /* ignore */
    }
  }, [storageKey]);

  // 1 分钟 tick
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  const next = lastUpdatedAt ? nextAvailableAt(new Date(lastUpdatedAt), cadence) : null;
  const isAvailable = !next || now >= next;

  const handleClick = useCallback(async () => {
    if (isUpdating || !isAvailable) return;
    setIsUpdating(true);
    setError(null);
    try {
      const res = await onRefresh();
      if (res.success) {
        const now = new Date().toISOString();
        try {
          localStorage.setItem(storageKey, now);
        } catch {
          /* ignore */
        }
        setLastUpdatedAt(now);
        setNow(new Date());
        onSuccess?.();
      } else {
        setError(res.message || res.error_code || '更新失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新失败');
    } finally {
      setIsUpdating(false);
    }
  }, [isUpdating, isAvailable, onRefresh, storageKey, onSuccess]);

  // 视觉：置灰且显示"下次更新 YYYY-MM"
  if (!isAvailable && next) {
    return (
      <button
        type="button"
        disabled
        className="px-4 py-2 rounded-lg bg-gray-800 text-gray-500 cursor-not-allowed flex items-center gap-2"
        title={`下次可更新：${next.toISOString().slice(0, 10)}`}
      >
        <span className="inline-block w-2 h-2 rounded-full bg-gray-600" />
        <span>下次更新：{formatDateForCadence(next, cadence)}</span>
      </button>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={handleClick}
        disabled={isUpdating}
        className={`px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2 ${
          isUpdating
            ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
            : 'bg-blue-600 text-white hover:bg-blue-500'
        }`}
      >
        {isUpdating ? (
          <>
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.3" />
              <path
                d="M4 12a8 8 0 018-8"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                fill="none"
              />
            </svg>
            更新中...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v6h6M20 20v-6h-6M4 10a8 8 0 0014 6M20 14a8 8 0 00-14-6" />
            </svg>
            {label}
          </>
        )}
      </button>
      {error && <span className="text-sm text-red-400">{error}</span>}
      {lastUpdatedAt && !error && (
        <span className="text-xs text-gray-500">
          上次更新：{new Date(lastUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
        </span>
      )}
    </div>
  );
}
