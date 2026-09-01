/**
 * 债基筛选主页
 */
'use client';

import { Suspense, useMemo, useState } from 'react';
import { FunnelIcon } from '@heroicons/react/24/outline';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { ExportCsvButton } from '@/components/ExportCsvButton';
import { RefreshStatusPopover } from '@/components/RefreshStatusPopover';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel } from '@/components/FilterSidebar';
import { FundTable } from '@/components/FundTable';
import { useCompare, useFeeDetails, useFundList } from '@/lib/hooks';
import {
  feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions,
} from '@/lib/compareDimensions';
import { useFilters } from '@/lib/useFilters';
import type { FundListItem } from '@/lib/types';

type NumFilterKey = 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp';

function FundsPageInner() {
  const { filters, setFilter, toggleSort, clearAll, activeCount } = useFilters();
  const { items, total, loading, error, reload } = useFundList(filters);
  const compare = useCompare<FundListItem>(5);
  const [sheetOpen, setSheetOpen] = useState(false);

  const compareDimensions = useMemo(
    () => [...fundCompareDimensions, ...fundDisplayOnlyDimensions, ...feeDetailDimensions],
    []
  );
  const selectedWithFees = useFeeDetails(compare.selected, compare.isDrawerOpen);

  return (
    <main className="min-h-screen pb-20">
      <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-ink-strong">债基筛选</h1>
          <div className="flex items-center gap-2 sm:gap-3">
            <ExportCsvButton filters={filters} />
            <RefreshStatusPopover onRefreshed={reload} />
            <span className="hidden sm:inline text-sm text-ink-muted">
              共 <span className="tnum font-semibold text-ink-strong">{total}</span> 只
            </span>
            <button
              onClick={() => setSheetOpen(true)}
              className="sm:hidden inline-flex items-center gap-1 px-2.5 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted"
              aria-label="打开筛选"
            >
              <FunnelIcon className="w-4 h-4" />
              筛选{activeCount > 0 && <span className="text-info">({activeCount})</span>}
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-4">
        <FilterChipBar
          filters={filters}
          onRemove={key => setFilter(key, null)}
        />
        <div className="grid grid-cols-1 sm:grid-cols-[260px_1fr] gap-4 items-start">
          <aside className="hidden sm:block sticky top-16">
            <FilterPanel
              filters={filters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
            />
          </aside>
          <section className="bg-paper-card rounded-lg border border-rule overflow-hidden">
            <FundTable
              items={items}
              loading={loading}
              error={error}
              sort={filters.sort}
              order={filters.order}
              onSort={toggleSort}
              isSelected={compare.isSelected}
              isCompareFull={compare.isFull}
              onToggleCompare={compare.toggle}
            />
          </section>
        </div>
      </div>

      <FilterSheet
        isOpen={sheetOpen}
        onClose={() => setSheetOpen(false)}
        filters={filters}
        onChange={(key: NumFilterKey, v) => setFilter(key, v)}
        onClearAll={clearAll}
        activeCount={activeCount}
      />

      <CompareFloatingBar
        selectedCount={compare.selected.length}
        selectedNames={compare.selected.map(s => s.name)}
        maxSelect={5}
        onOpenCompare={compare.openDrawer}
        onClear={compare.clearSelection}
        isVisible={!sheetOpen}
      />

      <CompareDrawer
        isOpen={compare.isDrawerOpen}
        onClose={compare.closeDrawer}
        items={selectedWithFees}
        dimensions={compareDimensions}
        onRemove={compare.removeItem}
      />
    </main>
  );
}

export default function FundsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <FundsPageInner />
    </Suspense>
  );
}
