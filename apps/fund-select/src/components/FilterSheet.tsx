/**
 * 移动端底部 sheet 筛选（≤640px），内嵌 FilterPanel
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';
import { useEffect } from 'react';

import type { FundFilters } from '@/lib/types';
import { FilterPanel } from './FilterSidebar';

interface FilterSheetProps {
  isOpen: boolean;
  onClose: () => void;
  filters: FundFilters;
  onChange: (key: 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp', value: number | null) => void;
  onClearAll: () => void;
  activeCount: number;
}

export function FilterSheet({ isOpen, onClose, filters, onChange, onClearAll, activeCount }: FilterSheetProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={onClose} aria-hidden="true" />
      <div
        className="fixed bottom-0 left-0 right-0 z-50 bg-paper rounded-t-2xl max-h-[80vh] overflow-y-auto lg:hidden"
        role="dialog"
        aria-modal="true"
        aria-label="筛选条件"
      >
        <div className="sticky top-0 bg-paper px-4 py-3 flex items-center justify-between border-b border-rule">
          <span className="font-semibold text-ink-strong">筛选</span>
          <button onClick={onClose} className="p-1 text-ink-muted hover:text-ink-strong" aria-label="关闭筛选">
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
        <div className="p-3">
          <FilterPanel filters={filters} onChange={onChange} onClearAll={onClearAll} activeCount={activeCount} />
          <button
            onClick={onClose}
            className="w-full mt-3 py-2.5 text-sm font-medium text-white bg-accent hover:bg-accent-hover rounded-lg"
          >
            查看结果
          </button>
        </div>
      </div>
    </>
  );
}
