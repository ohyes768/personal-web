/**
 * 筛选面板（桌面左侧 / 移动底部 sheet 复用同一表单）
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';

import type { FundFilters } from '@/lib/types';
import type { FilterKey, NumericFilterKey } from '@/lib/useFilters';

interface FilterPanelProps {
  filters: FundFilters;
  onChange: (key: FilterKey, value: number | boolean | null) => void;
  onClearAll: () => void;
  activeCount: number;
}

interface Dimension {
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

export function FilterPanel({ filters, onChange, onClearAll, activeCount }: FilterPanelProps) {
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
      {DIMENSIONS.map(dim => (
        <DimensionControl
          key={dim.key}
          dim={dim}
          value={filters[dim.key]}
          onChange={v => onChange(dim.key, v)}
        />
      ))}
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
