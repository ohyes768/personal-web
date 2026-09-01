/**
 * 筛选面板（桌面左侧 / 移动底部 sheet 复用同一表单）
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';

import type { FundFilters } from '@/lib/types';

interface FilterPanelProps {
  filters: FundFilters;
  onChange: (key: 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp', value: number | null) => void;
  onClearAll: () => void;
  activeCount: number;
}

interface Dimension {
  key: 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp';
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
}

const DIMENSIONS: Dimension[] = [
  { key: 'min_age', label: '成立年限', unit: '年', min: 0, max: 20, step: 0.5 },
  { key: 'min_size_yi', label: '规模', unit: '亿', min: 0, max: 350, step: 5 },
  { key: 'max_dd_3y', label: '近3年最大回撤', unit: '%', min: 0, max: 20, step: 0.5 },
  { key: 'min_mgr_exp', label: '经理从业年限', unit: '年', min: 0, max: 20, step: 0.5 },
];

function DimensionControl({ dim, value, onChange }: {
  dim: Dimension;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="px-4 py-3 border-b border-rule last:border-b-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-ink-strong">{dim.label}</span>
        <div className="flex items-center gap-1">
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
            className="w-16 px-2 py-1 text-right text-sm tnum border border-rule rounded bg-paper-card focus:outline-none focus:border-info"
            aria-label={`${dim.label}阈值`}
          />
          <span className="text-xs text-ink-soft">{dim.unit}</span>
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
      <input
        type="range"
        min={dim.min}
        max={dim.max}
        step={dim.step}
        value={value ?? dim.min}
        onChange={e => onChange(Number(e.target.value) === dim.min ? null : Number(e.target.value))}
        className="w-full accent-[var(--color-accent)]"
        aria-label={`${dim.label}滑块`}
      />
      <div className="flex justify-between text-[10px] text-ink-soft mt-0.5">
        <span>{dim.min}{dim.unit}</span>
        <span>{dim.max}{dim.unit}</span>
      </div>
    </div>
  );
}

export function FilterPanel({ filters, onChange, onClearAll, activeCount }: FilterPanelProps) {
  return (
    <div className="bg-paper-card rounded-lg border border-rule">
      <div className="px-4 py-3 border-b border-rule flex items-center justify-between">
        <span className="text-sm font-semibold text-ink-strong">筛选</span>
        <button
          onClick={onClearAll}
          disabled={activeCount === 0}
          className="text-xs text-ink-muted hover:text-down disabled:opacity-40 disabled:cursor-not-allowed"
        >
          清空全部
        </button>
      </div>
      {DIMENSIONS.map(dim => (
        <DimensionControl
          key={dim.key}
          dim={dim}
          value={filters[dim.key] as number | null}
          onChange={v => onChange(dim.key, v)}
        />
      ))}
    </div>
  );
}
