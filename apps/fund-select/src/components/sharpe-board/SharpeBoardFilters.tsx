/**
 * 夏普榜单展示筛选条：来源切换 + 夏普下限 + 至少上榜几周 + 只看最新周 + 时间范围
 *
 * 展示筛选只影响呈现，不改记录条件/历史数据（R5）；来源切换由父组件重置列表页
 * 并中止旧请求。390px 换行（flex-wrap）。
 */
'use client';

import type { ChangeEvent } from 'react';

import {
  RANGE_OPTIONS,
  SOURCE_OPTIONS,
  type SharpeBoardFilters,
  type SharpeRange,
  type SharpeSource,
} from '@/lib/sharpe-board';

interface SharpeBoardFiltersProps {
  filters: SharpeBoardFilters;
  onChange: (patch: Partial<SharpeBoardFilters>) => void;
}

const control =
  'px-2 py-1 rounded border border-rule bg-paper-card text-sm text-ink-strong focus-visible:outline-2 focus-visible:outline-info';
const labelCls = 'flex items-center gap-1.5 text-xs text-ink-muted whitespace-nowrap';

export function SharpeBoardFilters({ filters, onChange }: SharpeBoardFiltersProps) {
  function onMinSharpeChange(event: ChangeEvent<HTMLInputElement>) {
    const raw = event.target.value;
    if (raw === '') {
      onChange({ minLatestSharpe: null });
      return;
    }
    const v = Number(raw);
    if (Number.isFinite(v) && v >= -10 && v <= 10) {
      onChange({ minLatestSharpe: v });
    }
  }

  function onMinWeeksChange(event: ChangeEvent<HTMLInputElement>) {
    const v = Number(event.target.value);
    onChange({ minWeeks: Number.isInteger(v) && v >= 1 ? v : 1 });
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5 bg-paper-card rounded-lg border border-rule">
      {/* 来源切换（记录各自独立，切来源看不同榜单） */}
      <div className="flex items-center gap-1" role="group" aria-label="榜单来源">
        {SOURCE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange({ source: opt.value as SharpeSource })}
            aria-pressed={filters.source === opt.value}
            className={`px-2.5 py-1 rounded text-sm transition-colors ${
              filters.source === opt.value
                ? 'bg-accent text-white'
                : 'bg-paper-deep text-ink-muted hover:text-ink-strong'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <span className="w-px h-5 bg-rule" aria-hidden="true" />

      <label className={labelCls}>
        最近上榜夏普 ≥
        <input
          type="number"
          step={0.1}
          min={-10}
          max={10}
          value={filters.minLatestSharpe ?? ''}
          onChange={onMinSharpeChange}
          placeholder="不限"
          aria-label="最近上榜夏普下限（含等于）"
          className={`${control} w-20 tnum`}
        />
        {filters.minLatestSharpe !== null && (
          <button
            type="button"
            onClick={() => onChange({ minLatestSharpe: null })}
            className="text-info underline-offset-4 hover:underline"
            aria-label="清除夏普下限"
          >
            清除
          </button>
        )}
      </label>

      <label className={labelCls}>
        至少上榜
        <input
          type="number"
          min={1}
          value={filters.minWeeks}
          onChange={onMinWeeksChange}
          aria-label="至少上榜几周"
          className={`${control} w-14 tnum`}
        />
        周
      </label>

      <label className={labelCls}>
        <input
          type="checkbox"
          checked={filters.latestOnly}
          onChange={e => onChange({ latestOnly: e.target.checked })}
          className="accent-[#c56722]"
        />
        只看最新一周在榜
      </label>

      <label className={labelCls}>
        时间范围
        <select
          value={filters.range}
          onChange={e => onChange({ range: e.target.value as SharpeRange })}
          aria-label="图时间范围（只裁图，不改统计）"
          className={control}
        >
          {RANGE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
