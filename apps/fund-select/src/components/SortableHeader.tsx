/**
 * 可排序表头（三态：无 → desc → asc → 无）
 */
'use client';

import { ArrowDownIcon, ArrowUpIcon, ArrowsUpDownIcon } from '@heroicons/react/24/outline';

export type SortOrder = 'asc' | 'desc';

interface SortableHeaderProps {
  label: string;
  field: string;
  currentSort: string;
  currentOrder: SortOrder;
  onSort: (field: string) => void;
  align?: 'left' | 'right' | 'center';
  className?: string;
  /** 表头悬停说明（长文案，多行 + 靠右展开） */
  tip?: string;
}

export function SortableHeader({
  label, field, currentSort, currentOrder, onSort, align = 'right', className = '', tip = '',
}: SortableHeaderProps) {
  const active = currentSort === field;
  const Icon = !active ? ArrowsUpDownIcon : currentOrder === 'desc' ? ArrowDownIcon : ArrowUpIcon;

  const alignClass = align === 'left' ? 'text-left' : align === 'center' ? 'text-center' : 'text-right';

  return (
    <th className={`px-1.5 py-2 ${alignClass} ${className}`}>
      <button
        onClick={() => onSort(field)}
        className={`group inline-flex items-center gap-0.5 text-xs font-medium transition-colors ${
          active ? 'text-ink-strong' : 'text-ink-muted hover:text-ink-strong'
        }`}
        aria-label={`按${label}排序`}
      >
        <span
          className={tip ? 'hover-tip hover-tip--wrap hover-tip--right' : undefined}
          data-tip={tip || undefined}
        >
          {label}
        </span>
        <Icon className={`w-3 h-3 shrink-0 ${active ? 'opacity-100' : 'opacity-0 group-hover:opacity-40'}`} />
      </button>
    </th>
  );
}
