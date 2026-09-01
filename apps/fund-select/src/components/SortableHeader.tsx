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
}

export function SortableHeader({
  label, field, currentSort, currentOrder, onSort, align = 'right', className = '',
}: SortableHeaderProps) {
  const active = currentSort === field;
  const Icon = !active ? ArrowsUpDownIcon : currentOrder === 'desc' ? ArrowDownIcon : ArrowUpIcon;

  return (
    <th className={`px-3 py-2 text-${align} ${className}`}>
      <button
        onClick={() => onSort(field)}
        className={`inline-flex items-center gap-1 text-xs font-medium transition-colors ${
          active ? 'text-ink-strong' : 'text-ink-muted hover:text-ink-strong'
        }`}
        aria-label={`按${label}排序`}
      >
        <span className="whitespace-nowrap">{label}</span>
        <Icon className={`w-3 h-3 ${active ? 'opacity-100' : 'opacity-40'}`} />
      </button>
    </th>
  );
}
