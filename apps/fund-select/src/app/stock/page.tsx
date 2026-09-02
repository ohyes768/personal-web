/**
 * 股票基金筛选主页（/funds/stock）
 *
 * 与债基页（/funds）平列，复用：
 *   - FundsHeader（nav「债基 | 股票」）
 *   - FilterPanel / FilterSheet（4 维度筛选）
 *   - FilterChipBar / FundTable / CompareDrawer / CompareFloatingBar
 * 差异：
 *   - 默认值 STOCK_DEFAULT_FILTERS（3 / 5 / 5 / 20）
 *   - 调 stockApi（/api/funds/stock/*）
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
import { useCompare, useFeeDetails, useStockFundList } from '@/lib/hooks';
import {
  feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions,
} from '@/lib/compareDimensions';
import { useFilters } from '@/lib/useFilters';
import { STOCK_DEFAULT_FILTERS, type FundListItem } from '@/lib/types';

type NumFilterKey = 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp';

function StockFundsPageInner() {
  const { filters, setFilter, toggleSort, clearAll, activeCount } = useFilters(STOCK_DEFAULT_FILTERS);
  const { items, total, loading, error, reload } = useStockFundList(filters);
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
        active="stock"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        filters={filters}
        exportKind="stock"
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <FilterChipBar
          filters={filters}
          onRemove={key => setFilter(key, null)}
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
              showBondColumns={false}
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

export default function StockFundsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <StockFundsPageInner />
    </Suspense>
  );
}
