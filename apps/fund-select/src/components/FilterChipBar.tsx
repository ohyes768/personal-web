/**
 * 顶部筛选 chip：显示已选条件，点 × 移除
 */
'use client';

import { XMarkIcon, FunnelIcon } from '@heroicons/react/24/outline';

import type { FundFilters } from '@/lib/types';
import type { FilterKey, NumericFilterKey } from '@/lib/useFilters';

interface FilterChipBarProps {
  filters: Pick<FundFilters, NumericFilterKey | 'exclude_qdii'>;
  onRemove: (key: FilterKey) => void;
}

const LABELS: Record<NumericFilterKey, { label: string; fmt: (v: number) => string }> = {
  min_age: { label: '成立年限', fmt: v => `≥ ${v} 年` },
  min_size_yi: { label: '规模', fmt: v => `≥ ${v} 亿` },
  max_dd_3y: { label: '近3年回撤', fmt: v => `≤ ${v}%` },
  min_mgr_exp: { label: '经理从业', fmt: v => `≥ ${v} 年` },
};

const NUMERIC_KEYS = Object.keys(LABELS) as NumericFilterKey[];

export function FilterChipBar({ filters, onRemove }: FilterChipBarProps) {
  const activeNumeric = NUMERIC_KEYS.filter(k => filters[k] !== null);
  const hasQdii = filters.exclude_qdii;

  if (activeNumeric.length === 0 && !hasQdii) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-ink-soft py-1.5">
        <FunnelIcon className="w-3.5 h-3.5" />
        未筛选
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap py-1.5">
      {activeNumeric.map(key => {
        const v = filters[key] as number;
        const meta = LABELS[key];
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info"
          >
            {meta.label} {meta.fmt(v)}
            <button
              onClick={() => onRemove(key)}
              className="hover:text-down"
              aria-label={`移除${meta.label}筛选`}
            >
              <XMarkIcon className="w-3 h-3" />
            </button>
          </span>
        );
      })}
      {hasQdii && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info">
          排除 QDII
          <button
            onClick={() => onRemove('exclude_qdii')}
            className="hover:text-down"
            aria-label="移除排除 QDII"
          >
            <XMarkIcon className="w-3 h-3" />
          </button>
        </span>
      )}
    </div>
  );
}
