'use client';

/**
 * 发布日历(6×7 周一起始)
 * - 根据发布规则在每天画对应分组的色点
 * - 点击日期弹出 popover 显示当天发布的分组列表
 * - 今日蓝边框高亮,未来日期灰显
 */
import { useState, useMemo, useRef, useEffect } from 'react';
import type { DimensionKey } from '@/lib/modules/macro-signal/types';
import { GROUP_META, GROUP_ORDER } from './constants';
import { getReleaseCalendar } from '@/lib/modules/macro-signal/release-rules';

interface ReleaseCalendarProps {
  month: string;                    // 'YYYY-MM'
}

function formatMonthTitle(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return `发布日历 · ${y} 年 ${m} 月`;
}

export function ReleaseCalendar({ month }: ReleaseCalendarProps) {
  const [popover, setPopover] = useState<{ iso: string; dims: DimensionKey[]; anchor: DOMRect } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 计算发布日期 map
  const releaseMap = useMemo(() => getReleaseCalendar(month), [month]);

  // 关闭 popover(点击外部)
  useEffect(() => {
    if (!popover) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setPopover(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [popover]);

  // 构造日历单元格
  const [year, mon] = month.split('-').map(Number);
  const firstDay = new Date(Date.UTC(year, mon - 1, 1));
  const lastDay = new Date(Date.UTC(year, mon, 0));
  let startWeekday = firstDay.getUTCDay();      // 0=Sun
  startWeekday = startWeekday === 0 ? 6 : startWeekday - 1;  // 周一=0
  const totalDays = lastDay.getUTCDate();
  const todayISO = new Date().toISOString().slice(0, 10);

  const cells: Array<{ day: number; iso: string } | null> = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= totalDays; d++) {
    const iso = new Date(Date.UTC(year, mon - 1, d)).toISOString().slice(0, 10);
    cells.push({ day: d, iso });
  }

  return (
    <section className="bg-gray-900 rounded-lg p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h2 className="text-lg font-semibold">{formatMonthTitle(month)}</h2>
        <div className="flex items-center gap-3 text-xs flex-wrap">
          {GROUP_ORDER.map(key => (
            <span key={key} className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${GROUP_META[key].calendarColor}`}></span>
              <span className="text-gray-400">{GROUP_META[key].title}</span>
            </span>
          ))}
        </div>
      </div>

      <div ref={containerRef} className="grid grid-cols-7 gap-1">
        {/* 表头 */}
        {['一', '二', '三', '四', '五', '六', '日'].map(w => (
          <div key={w} className="text-center text-xs text-gray-500 py-1">{w}</div>
        ))}

        {/* 日期单元格 */}
        {cells.map((cell, idx) => {
          if (!cell) {
            return <div key={`blank-${idx}`} className="h-16 rounded bg-gray-900/30"></div>;
          }
          const isPast = cell.iso < todayISO;
          const isToday = cell.iso === todayISO;
          const dims = releaseMap[cell.iso] || [];
          const hasReleases = dims.length > 0;

          const cellClass = isToday
            ? 'h-16 rounded border border-blue-500 bg-blue-900/20 p-1.5 cursor-pointer relative transition-colors'
            : isPast
              ? `h-16 rounded border border-gray-800 bg-gray-900 p-1.5 relative transition-colors ${hasReleases ? 'cursor-pointer hover:bg-gray-800' : ''}`
              : 'h-16 rounded border border-gray-900 bg-gray-900/40 p-1.5 opacity-50 relative';

          const handleCellClick = (e: React.MouseEvent<HTMLButtonElement>) => {
            if (!hasReleases) return;
            const rect = e.currentTarget.getBoundingClientRect();
            setPopover({ iso: cell.iso, dims, anchor: rect });
          };

          return (
            <button
              type="button"
              key={cell.iso}
              onClick={handleCellClick}
              disabled={!hasReleases}
              className={cellClass}
            >
              <div className={`text-xs text-left ${
                isToday ? 'text-blue-300 font-bold' : isPast ? 'text-gray-300' : 'text-gray-600'
              }`}>
                {cell.day}
              </div>
              {hasReleases && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {dims.slice(0, 6).map(k => (
                    <span key={k} className={`w-1.5 h-1.5 rounded-full ${GROUP_META[k].calendarColor}`}></span>
                  ))}
                </div>
              )}
            </button>
          );
        })}
      </div>

      <p className="text-xs text-gray-500 mt-3">点击有发布指标的日期可查看详情。色点仅区分维度身份。</p>

      {/* Popover */}
      {popover && (
        <div
          className="fixed z-50 bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl w-56"
          style={{
            top: `${popover.anchor.bottom + 4}px`,
            left: `${popover.anchor.left}px`,
          }}
        >
          <div className="text-xs text-gray-400 mb-2 font-mono">{popover.iso}</div>
          {popover.dims.map(k => (
            <div key={k} className="flex items-center gap-2 text-sm py-1">
              <span className={`w-2 h-2 rounded-full ${GROUP_META[k].calendarColor}`}></span>
              <span className="text-gray-200">{GROUP_META[k].title}</span>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setPopover(null)}
            className="mt-2 text-xs text-gray-500 hover:text-gray-300"
          >
            关闭
          </button>
        </div>
      )}
    </section>
  );
}
