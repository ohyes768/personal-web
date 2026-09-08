/**
 * 筛选面板（桌面左侧 / 移动底部 sheet 复用同一表单）
 *
 * dimensions: 数值维度 + 可选的 market_types 多选维度
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';

import { MARKET_TYPE_OPTIONS, type FundFilters } from '@/lib/types';
import type { FilterKey, NumericFilterKey } from '@/lib/useFilters';

interface FilterPanelProps {
  filters: FundFilters;
  onChange: (key: FilterKey, value: number | boolean | string[] | null) => void;
  onClearAll: () => void;
  activeCount: number;
  /** 老 tab（bond / stock）不传；market tab 传 true 显示基金类型多选 */
  showMarketTypes?: boolean;
  dimensions?: Dimension[];
}

export interface Dimension {
  key: NumericFilterKey;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
}

const DIMENSIONS: Dimension[] = [
  { key: 'min_age', label: '年限', unit: '年', min: 0, max: 20, step: 0.5 },
  { key: 'min_size_yi', label: '规模', unit: '亿', min: 0, max: 350, step: 5 },
  { key: 'max_dd_3y', label: '3年回撤', unit: '%', min: 0, max: 20, step: 0.5 },
  { key: 'min_mgr_exp', label: '经理', unit: '年', min: 0, max: 20, step: 0.5 },
];

/** 股票 / 市场股基 tab 维度：四维 + 夏普（近 3 年，范围参考宇宙分布 -0.1 ~ 1.6） */
export const STOCK_DIMENSIONS: Dimension[] = [
  ...DIMENSIONS,
  { key: 'min_sharpe', label: '夏普', unit: '', min: -1, max: 2, step: 0.1 },
];

function DimensionControl({ dim, value, onChange }: {
  dim: Dimension;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="px-2.5 py-2 border-b border-rule last:border-b-0">
      <div className="flex items-center justify-between gap-1">
        <span className="text-xs font-medium text-ink-strong shrink-0">{dim.label}</span>
        <div className="flex items-center gap-0.5 min-w-0">
          <input
            type="number"
            min={dim.min}
            max={dim.max}
            step={dim.step}
            value={value ?? ''}
            placeholder="不限"
            onChange={e => {
              const raw = e.target.value;
              onChange(raw === '' ? null : Number(raw));
            }}
            className="w-12 px-1 py-0.5 text-right text-xs tnum border border-rule rounded bg-paper-card focus:outline-none focus:border-info"
            aria-label={`${dim.label}阈值`}
          />
          <span className="text-[10px] text-ink-soft">{dim.unit}</span>
          {value !== null && (
            <button
              onClick={() => onChange(null)}
              className="p-0.5 text-ink-soft hover:text-down"
              aria-label={`清除${dim.label}筛选`}
            >
              <XMarkIcon className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function MarketTypeControl({
  value, onChange,
}: {
  value: string[] | null;
  onChange: (next: string[] | null) => void;
}) {
  const selected = value ?? [];
  const toggle = (v: string) => {
    const next = selected.includes(v)
      ? selected.filter(x => x !== v)
      : [...selected, v];
    onChange(next.length > 0 ? next : null);
  };

  return (
    <div className="px-2.5 py-2 border-b border-rule">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-ink-strong">基金类型</span>
        {selected.length > 0 && (
          <button
            onClick={() => onChange(null)}
            className="text-[11px] text-ink-soft hover:text-down"
            aria-label="清空基金类型筛选"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1">
        {MARKET_TYPE_OPTIONS.map(opt => {
          const checked = selected.includes(opt.value);
          return (
            <label
              key={opt.value}
              className="flex items-center gap-1 text-[11px] text-ink-muted cursor-pointer"
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(opt.value)}
                className="rounded border-rule text-info focus:ring-info"
                aria-label={`筛选 ${opt.label}`}
              />
              {opt.label}
            </label>
          );
        })}
      </div>
    </div>
  );
}

export function FilterPanel({
  filters, onChange, onClearAll, activeCount,
  showMarketTypes = false, dimensions = DIMENSIONS,
}: FilterPanelProps) {
  return (
    <div className="bg-paper-card rounded-lg border border-rule">
      <div className="px-2.5 py-2 border-b border-rule flex items-center justify-between gap-1">
        <span className="text-xs font-semibold text-ink-strong">筛选</span>
        <button
          onClick={onClearAll}
          disabled={activeCount === 0}
          className="text-[11px] text-ink-muted hover:text-down disabled:opacity-40 disabled:cursor-not-allowed"
        >
          清空
        </button>
      </div>
      {dimensions.map(dim => (
        <DimensionControl
          key={dim.key}
          dim={dim}
          value={filters[dim.key]}
          onChange={v => onChange(dim.key, v)}
        />
      ))}
      {showMarketTypes && (
        <MarketTypeControl
          value={filters.market_types}
          onChange={next => onChange('market_types', next)}
        />
      )}
      <label className="px-2.5 py-2 flex items-center gap-1.5 cursor-pointer">
        <input
          type="checkbox"
          checked={filters.exclude_qdii}
          onChange={e => onChange('exclude_qdii', e.target.checked)}
          className="rounded border-rule text-info focus:ring-info"
          aria-label="排除 QDII"
        />
        <span className="text-xs font-medium text-ink-strong">排除 QDII</span>
      </label>
    </div>
  );
}
