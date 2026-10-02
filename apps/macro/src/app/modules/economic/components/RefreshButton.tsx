'use client';

/**
 * 数据更新按钮
 * - 数据驱动（daily 且传了 dataLastDate 时优先）：数据最后日期距今天 ≤ 4 天
 *   → 置灰显示「数据截至 MM-DD」（定时任务每天自动更新，无需手动点）；
 *   停更超期 → 高亮可点，提示「数据停在 MM-DD」
 *   （4 天容差覆盖周末 + 3 天小长假；长假后按钮亮一下属预期，点一次即恢复）
 * - 旧逻辑兜底（monthly / 无 dataLastDate）：更新后置灰到下个月 1 号 / 明天 00:00，
 *   通过 localStorage 持久化 lastUpdatedAt
 */
import { useState, useEffect, useCallback } from 'react';
import type { UpdateResponse } from '@/lib/modules/economic/api';

export type RefreshCadence = 'monthly' | 'daily';

/** daily 数据视为「新鲜」的最大天数间隔 */
const FRESH_TOLERANCE_DAYS = 4;

interface RefreshButtonProps {
  onRefresh: () => Promise<UpdateResponse>;
  storageKey: string;
  cadence: RefreshCadence;
  label: string;
  /** 本 Tab 数据「最后有数据点」的日期 'YYYY-MM-DD'（数据驱动亮/灰的依据） */
  dataLastDate?: string | null;
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

/** 'YYYY-MM-DD' 距今天隔了几天（本地时间，负数=未来日期按 0 算） */
function daysAgo(dateStr: string): number {
  const d = new Date(dateStr + 'T00:00:00');
  if (isNaN(d.getTime())) return Number.POSITIVE_INFINITY; // 非法日期视为停更
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((today.getTime() - d.getTime()) / 86_400_000));
}

export function RefreshButton({ onRefresh, storageKey, cadence, label, dataLastDate, onSuccess }: RefreshButtonProps) {
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

  // 数据驱动：daily 且拿到数据最后日期 → 数据新鲜即置灰（定时任务已覆盖，无需手点）
  const dataDriven = cadence === 'daily' && dataLastDate != null;
  const dataAge = dataDriven ? daysAgo(dataLastDate as string) : null;
  const isDataFresh = dataAge != null && dataAge <= FRESH_TOLERANCE_DAYS;

  const isAvailable = dataDriven ? !isDataFresh : (!next || now >= next);

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

  // 视觉：置灰。数据驱动 → 「数据截至 MM-DD」；旧逻辑 → 「下次更新 YYYY-MM」
  if (!isAvailable) {
    const disabledContent = dataDriven ? (
      <>
        <span className="inline-block w-2 h-2 rounded-full bg-green-700" />
        <span>数据截至 {(dataLastDate as string).slice(5)}</span>
      </>
    ) : next ? (
      <>
        <span className="inline-block w-2 h-2 rounded-full bg-gray-600" />
        <span>下次更新：{formatDateForCadence(next, cadence)}</span>
      </>
    ) : null;
    if (disabledContent) {
      return (
        <button
          type="button"
          disabled
          className="px-4 py-2 rounded-lg bg-gray-800 text-gray-500 cursor-not-allowed flex items-center gap-2"
          title={dataDriven ? '数据已是最新（定时任务每天自动更新），无需手动更新' : next ? `下次可更新：${formatDateForCadence(next, cadence)}` : ''}
        >
          {disabledContent}
        </button>
      );
    }
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
      {!error && dataDriven && !isDataFresh && dataLastDate && (
        <span className="text-xs text-amber-400/90">数据停在 {(dataLastDate as string).slice(5)} · 点击拉取</span>
      )}
      {!error && !(dataDriven && !isDataFresh) && lastUpdatedAt && (
        <span className="text-xs text-gray-500">
          上次更新：{new Date(lastUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
        </span>
      )}
    </div>
  );
}
