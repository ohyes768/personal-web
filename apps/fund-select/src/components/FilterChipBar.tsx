/**
 * 顶部筛选 chip：显示已选条件，点 × 移除
 */
'use client';

import { XMarkIcon, FunnelIcon } from '@heroicons/react/24/outline';

interface FilterChipBarProps {
  filters: {
    min_age: number | null;
    min_size_yi: number | null;
    max_dd_3y: number | null;
    min_mgr_exp: number | null;
  };
  onRemove: (key: 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp') => void;
}

const LABELS: Record<string, { label: string; fmt: (v: number) => string }> = {
  min_age: { label: '成立年限', fmt: v => `≥ ${v} 年` },
  min_size_yi: { label: '规模', fmt: v => `≥ ${v} 亿` },
  max_dd_3y: { label: '近3年回撤', fmt: v => `≤ ${v}%` },
  min_mgr_exp: { label: '经理从业', fmt: v => `≥ ${v} 年` },
};

export function FilterChipBar({ filters, onRemove }: FilterChipBarProps) {
  const active = (Object.keys(LABELS) as Array<keyof typeof LABELS>).filter(
    k => filters[k as keyof typeof filters] !== null
  );

  if (active.length === 0) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-ink-soft py-1.5">
        <FunnelIcon className="w-3.5 h-3.5" />
        未筛选
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap py-1.5">
      {active.map(key => {
        const v = filters[key as keyof typeof filters] as number;
        const meta = LABELS[key];
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info"
          >
            {meta.label} {meta.fmt(v)}
            <button
              onClick={() => onRemove(key as 'min_age')}
              className="hover:text-down"
              aria-label={`移除${meta.label}筛选`}
            >
              <XMarkIcon className="w-3 h-3" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
