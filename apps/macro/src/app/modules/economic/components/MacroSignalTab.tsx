'use client';

/**
 * 宏观信号 Tab 容器组件(信号首页)
 * - 单页双区块:月度信号(4 卡+档位刻度)与日频信号(3 卡+日变化)上下并行展示
 * - 月度区块:loadSnapshot + availableMonths,默认上个月(数据完整月)
 * - 日频区块:/api/macro/daily-snapshot,默认日期由后端 15:00 规则推导
 *   (首拉不带 date 采纳响应 date,用户手动切换才显式传 date → 前后端规则天然一致)
 * - 两区块状态独立:任一请求失败只影响本区块,切月/切日互不干扰
 */
import { useState, useEffect, useMemo } from 'react';
import { MonthSwitcher } from './macro-signal/MonthSwitcher';
import { DailySwitcher } from './macro-signal/DailySwitcher';
import { GroupCardGrid } from './macro-signal/GroupCardGrid';
import { DailyCardGrid } from './macro-signal/DailyCardGrid';
import { GROUP_ORDER, MONTHLY_GROUPS } from './macro-signal/constants';
import type {
  DailySnapshot,
  DimensionKey,
  MacroSignalGroup,
  MacroSignalSnapshot,
  MacroSignalTabProps,
} from '@/lib/modules/macro-signal/types';

/** availableMonths 异步未就绪时,fallback 到当前真实月份,让月份选择器至少有值 */
function currentYearMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** 上个月 'YYYY-MM'(setDate(0) 回到上月末,避开 setMonth 在月末日期的溢出问题) */
function prevYearMonth(): string {
  const d = new Date();
  d.setDate(0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** 'YYYY-MM-DD' → 'M 月 D 日'(日频区块头「截至」文案用) */
function formatDateLabel(date: string): string {
  const [, m, d] = date.split('-');
  return `${parseInt(m, 10)} 月 ${parseInt(d, 10)} 日`;
}

/** 空快照:snapshot 接口返回 null 时构造,月度四维仍展示「数据缺失」态 */
function emptySnapshot(month: string): MacroSignalSnapshot {
  const groups = GROUP_ORDER.reduce<Record<DimensionKey, MacroSignalGroup>>((acc, key) => {
    acc[key] = { conclusion: null, indicators: [] };
    return acc;
  }, {} as Record<DimensionKey, MacroSignalGroup>);
  return { month, groups };
}

/**
 * 月度默认月份:上个月;上个月无数据时回退到 availableMonths 中早于当月的最近月份,
 * 全部不满足再回退到最大月份(当月,看「暂未获取」占位)
 */
function pickDefaultMonth(availableMonths: string[], initialMonth?: string): string {
  if (initialMonth) return initialMonth;
  const lastMonth = prevYearMonth();
  if (availableMonths.length === 0 || availableMonths.includes(lastMonth)) return lastMonth;
  const earlier = availableMonths.filter(m => m < currentYearMonth()).sort();
  return earlier.length > 0 ? earlier[earlier.length - 1] : availableMonths[availableMonths.length - 1];
}

export function MacroSignalTab({ loadSnapshot, initialMonth, onJumpToTab }: MacroSignalTabProps) {
  // === 月度区块状态 ===
  // 懒加载可用月份：仅在 MacroSignalTab 实际挂载时才发请求
  const [availableMonths, setAvailableMonths] = useState<string[]>([]);
  useEffect(() => {
    fetch('/api/macro/months')
      .then(r => (r.ok ? r.json() : { months: [] }))
      .then(d => setAvailableMonths(Array.isArray(d?.months) ? d.months : []))
      .catch(() => { /* 后端未启动时保持空数组,MonthSwitcher 会 fallback 到当前月 */ });
  }, []);

  // 当前自然月始终可选:当月尚无数据时也要能切进去看「暂未获取+预期发布」
  const monthsWithNow = useMemo(
    () => Array.from(new Set([...availableMonths, currentYearMonth()])).sort(),
    [availableMonths],
  );

  // 默认上个月;availableMonths 就绪后,若当前选择不在可选列表里(如上个月无数据)再校正
  const [selectedMonth, setSelectedMonth] = useState<string>(() => pickDefaultMonth([], initialMonth));
  const [snapshot, setSnapshot] = useState<MacroSignalSnapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (availableMonths.length === 0) return;
    if (monthsWithNow.includes(selectedMonth)) return;
    setSelectedMonth(pickDefaultMonth(availableMonths, initialMonth));
  }, [availableMonths, monthsWithNow, selectedMonth, initialMonth]);

  useEffect(() => {
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

  // === 日频区块状态 ===
  // selectedDate 只在用户手动切换时赋值;首拉(=null)不带 date,由后端 15:00 规则推导,
  // 渲染用 effectiveDate = selectedDate ?? dailySnapshot.date
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [dailySnapshot, setDailySnapshot] = useState<DailySnapshot | null>(null);
  const [dailyLoading, setDailyLoading] = useState<boolean>(false);
  const [dailyError, setDailyError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDailyLoading(true);
    setDailyError(null);
    const qs = selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : '';
    fetch(`/api/macro/daily-snapshot${qs}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body: { success?: boolean; data?: DailySnapshot }) => {
        if (cancelled) return;
        if (!body?.data) throw new Error('响应缺少 data 字段');
        setDailySnapshot(body.data);
      })
      .catch(err => {
        if (cancelled) return;
        setDailyError(err instanceof Error ? err.message : String(err));
        setDailySnapshot(null);
      })
      .finally(() => {
        if (!cancelled) setDailyLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedDate]);

  const effectiveDate = selectedDate ?? dailySnapshot?.date ?? '';

  return (
    <div className="space-y-5">
      {/* 区块一:月度信号(标题 + 月份选择器 + 4 卡) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h3 className="text-sm font-medium text-gray-400">月度信号</h3>
          <MonthSwitcher
            currentMonth={selectedMonth}
            availableMonths={monthsWithNow}
            onChange={setSelectedMonth}
          />
        </div>

        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {Array.from({ length: MONTHLY_GROUPS.length }).map((_, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-3 h-36 animate-pulse">
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
      </section>

      {/* 区块二:日频信号(标题「截至 M 月 D 日」+ 日期选择器 + 3 卡) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h3 className="text-sm font-medium text-gray-400">
            日频信号{effectiveDate ? ` · 截至 ${formatDateLabel(effectiveDate)}` : ''}
          </h3>
          <DailySwitcher
            currentDate={effectiveDate}
            availableDates={dailySnapshot?.dates ?? []}
            onChange={setSelectedDate}
          />
        </div>

        {dailyLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-3 h-28 animate-pulse">
                <div className="h-3 w-20 bg-gray-800 rounded mb-3"></div>
                <div className="h-5 w-16 bg-gray-800 rounded mb-4"></div>
                <div className="h-3 w-full bg-gray-800 rounded mb-2"></div>
                <div className="h-3 w-3/4 bg-gray-800 rounded mb-2"></div>
                <div className="h-3 w-2/3 bg-gray-800 rounded"></div>
              </div>
            ))}
          </div>
        )}

        {!dailyLoading && dailyError && (
          <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-red-200 mb-2">加载失败</p>
            <p className="text-red-400 text-sm font-mono">{dailyError}</p>
          </div>
        )}

        {!dailyLoading && !dailyError && dailySnapshot && (
          <DailyCardGrid snapshot={dailySnapshot} onJumpToTab={onJumpToTab} />
        )}
      </section>
    </div>
  );
}
