'use client';

/**
 * 宏观信号 Tab 容器组件
 * - 接收 loadSnapshot + availableMonths + initialMonth?
 * - 内部 useEffect 监听 selectedMonth 变化,触发 loadSnapshot
 * - 管理 loading / error / snapshot 三态
 */
import { useState, useEffect } from 'react';
import { MonthSwitcher } from './macro-signal/MonthSwitcher';
import { GroupCardGrid } from './macro-signal/GroupCardGrid';
import { ReleaseCalendar } from './macro-signal/ReleaseCalendar';
import { GROUP_ORDER } from './macro-signal/constants';
import type { DimensionKey, MacroSignalGroup, MacroSignalSnapshot, MacroSignalTabProps } from '@/lib/modules/macro-signal/types';

/** availableMonths 异步未就绪时,fallback 到当前真实月份,让月份选择器至少有值 */
function currentYearMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** 空快照:snapshot 接口返回 null 时构造,让六大维度卡片仍展示「数据缺失」态 */
function emptySnapshot(month: string): MacroSignalSnapshot {
  const groups = GROUP_ORDER.reduce<Record<DimensionKey, MacroSignalGroup>>((acc, key) => {
    acc[key] = { conclusion: null, indicators: [] };
    return acc;
  }, {} as Record<DimensionKey, MacroSignalGroup>);
  return { month, groups };
}

export function MacroSignalTab({ loadSnapshot, availableMonths, initialMonth, onJumpToTab }: MacroSignalTabProps) {
  const sorted = [...availableMonths].sort();
  const defaultMonth = initialMonth ?? sorted[sorted.length - 1] ?? currentYearMonth();

  const [selectedMonth, setSelectedMonth] = useState<string>(defaultMonth);
  const [snapshot, setSnapshot] = useState<MacroSignalSnapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showCalendar, setShowCalendar] = useState<boolean>(false);

  useEffect(() => {
    // 月份未就绪（availableMonths 还在加载）时不发请求，避免 month=undefined 触发 404
    if (!selectedMonth) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadSnapshot(selectedMonth)
      .then(snap => {
        if (cancelled) return;
        setSnapshot(snap);
      })
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setSnapshot(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedMonth, loadSnapshot]);

  // availableMonths 异步就绪后，补选最近月份
  // （首次 render 时 months 为空 → selectedMonth 为 undefined；months 到位后这里补上）
  useEffect(() => {
    if (!selectedMonth && defaultMonth) {
      setSelectedMonth(defaultMonth);
    }
  }, [selectedMonth, defaultMonth]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 mb-8 flex-wrap">
        <MonthSwitcher
          currentMonth={selectedMonth}
          availableMonths={availableMonths}
          onChange={setSelectedMonth}
        />
        <button
          type="button"
          onClick={() => setShowCalendar(true)}
          className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
        >
          📅 发布日历
        </button>
      </div>

      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-5 h-48 animate-pulse">
              <div className="h-3 w-20 bg-gray-800 rounded mb-3"></div>
              <div className="h-5 w-16 bg-gray-800 rounded mb-4"></div>
              <div className="h-3 w-full bg-gray-800 rounded mb-2"></div>
              <div className="h-3 w-3/4 bg-gray-800 rounded mb-2"></div>
              <div className="h-3 w-2/3 bg-gray-800 rounded"></div>
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">加载失败</p>
          <p className="text-red-400 text-sm font-mono">{error}</p>
        </div>
      )}

      {!loading && !error && (
        <GroupCardGrid
          snapshot={snapshot ?? emptySnapshot(selectedMonth)}
          selectedMonth={selectedMonth}
          onJumpToTab={onJumpToTab}
        />
      )}

      {/* 发布日历弹框 */}
      {showCalendar && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowCalendar(false)}
        >
          <div
            className="max-w-3xl w-full max-h-[90vh] overflow-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex justify-end mb-2">
              <button
                type="button"
                onClick={() => setShowCalendar(false)}
                className="px-3 py-1 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm"
              >
                ✕ 关闭
              </button>
            </div>
            <ReleaseCalendar month={selectedMonth} />
          </div>
        </div>
      )}
    </div>
  );
}
