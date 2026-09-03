/**
 * 债券基金筛选主页（/funds/bond），与股票页（/funds/stock）平列
 */
'use client';

import { Suspense, useMemo, useState } from 'react';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { FundTable } from '@/components/FundTable';
import { useCompare, useFeeDetails, useFundList } from '@/lib/hooks';
import {
  feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions,
} from '@/lib/compareDimensions';
import { useFilters } from '@/lib/useFilters';
import type { FundListItem } from '@/lib/types';

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
      <FundsHeader
        active="bond"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        filters={filters}
        exportKind="bond"
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <FilterChipBar
          filters={filters}
          onRemove={key => setFilter(key, key === 'exclude_qdii' ? false : null)}
        />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={filters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
            />
          </aside>
          <section className="min-w-0 overflow-x-clip bg-paper-card rounded-lg border border-rule">
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
        onChange={(key, v) => setFilter(key, v)}
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
