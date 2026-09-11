/**
 * 债基·市场 tab 主页（/funds/discovery-bond）
 *
 * 与债基 tab（/funds/bond）平列，复用 FundsHeader / FilterPanel / FundTable / CompareDrawer 等；
 * 差异：
 *   - 默认值 DISCOVERY_BOND_DEFAULT_FILTERS（含默认 market_types = 10 个债券子类）
 *   - 调 discoveryBondApi（/api/funds/discovery-bond/*）
 *   - 筛选面板多一栏「基金类型」多选
 *   - 「全量刷新」按钮：触发 4 阶段流水线，完成后把预筛选值同步到左侧（disabled 不可改）
 *   - 隐藏「排除 QDII」复选框（QDII 不在债基·市场 universe）
 */
'use client';

import { Suspense, useCallback, useMemo, useState } from 'react';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { FundTable } from '@/components/FundTable';
import { Pagination } from '@/components/Pagination';
import { RowDetailDrawerBond } from '@/components/RowDetailDrawerBond';
import { useCompare, useDiscoveryBondFundList, useFeeDetails } from '@/lib/hooks';
import { feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions } from '@/lib/compareDimensions';
import { useFilters } from '@/lib/useFilters';
import {
  BOND_MARKET_TYPE_OPTIONS,
  DEFAULT_FULL_REFRESH_FILTERS_BOND,
  DISCOVERY_BOND_DEFAULT_FILTERS,
  type FullRefreshFilters,
  type FundListItem,
} from '@/lib/types';

/** 全量 refresh 完成后，左侧筛选面板锁定的 3 个预筛字段 */
const LOCKED_PRE_FILTERS = ['min_ret_3y', 'min_size_yi', 'min_mgr_exp'];

function DiscoveryBondPageInner() {
  const { filters, setFilter, toggleSort, clearAll, setPage, setLimit, activeCount } = useFilters(DISCOVERY_BOND_DEFAULT_FILTERS);
  const { items, total, loading, error, reload } = useDiscoveryBondFundList(filters);
  const compare = useCompare<FundListItem>(5);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detailFund, setDetailFund] = useState<FundListItem | null>(null);

  // 预筛选值（来自全量 refresh 完成时回写；lockedFields 在左侧 disabled）
  const [preFilters, setPreFilters] = useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS_BOND);

  const handleFullRefreshComplete = useCallback((pf: FullRefreshFilters) => {
    setPreFilters(pf);
  }, []);

  // 把预筛选值合并到 filters（locked 后用户改不动）
  const effectiveFilters = useMemo(() => ({
    ...filters,
    min_ret_3y: preFilters.min_ret_3y,
    min_size_yi: preFilters.min_size_yi,
    min_mgr_exp: preFilters.min_mgr_exp,
  }), [filters, preFilters]);

  const compareDimensions = useMemo(
    () => [...fundCompareDimensions, ...fundDisplayOnlyDimensions, ...feeDetailDimensions],
    []
  );
  const selectedWithFees = useFeeDetails(compare.selected, compare.isDrawerOpen);

  const handleRemove = (key: string, value?: string) => {
    if (key === 'market_types' && value) {
      const next = (filters.market_types ?? []).filter(t => t !== value);
      setFilter('market_types', next.length > 0 ? next : null);
      return;
    }
    if (key === 'exclude_qdii') {
      setFilter('exclude_qdii', false);
      return;
    }
    setFilter(key as 'min_age' | 'min_size_yi' | 'max_dd_3y' | 'min_mgr_exp' | 'min_sharpe', null);
  };

  return (
    <main className="min-h-screen pb-20">
      <FundsHeader
        active="discovery-bond"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        filters={filters}
        exportKind="discovery-bond"
        onFullRefreshComplete={handleFullRefreshComplete}
        preFilters={preFilters}
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <FilterChipBar filters={effectiveFilters} onRemove={handleRemove} />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={effectiveFilters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
              showMarketTypes
              marketTypeOptions={BOND_MARKET_TYPE_OPTIONS}
              hideExcludeQdii
              lockedFields={LOCKED_PRE_FILTERS}
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
              showBondColumns
              onRowClick={setDetailFund}
              ddBarCapPct={20}
              marketKind="bond"
            />
            <Pagination
              page={filters.page}
              limit={filters.limit}
              total={total}
              onPageChange={setPage}
              onLimitChange={setLimit}
            />
          </section>
        </div>
      </div>

      <FilterSheet
        isOpen={sheetOpen}
        onClose={() => setSheetOpen(false)}
        filters={effectiveFilters}
        onChange={(key, v) => setFilter(key, v)}
        onClearAll={clearAll}
        activeCount={activeCount}
        showMarketTypes
        marketTypeOptions={BOND_MARKET_TYPE_OPTIONS}
        hideExcludeQdii
        lockedFields={LOCKED_PRE_FILTERS}
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

      <RowDetailDrawerBond
        fund={detailFund}
        onClose={() => setDetailFund(null)}
      />
    </main>
  );
}

export default function DiscoveryBondPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <DiscoveryBondPageInner />
    </Suspense>
  );
}
