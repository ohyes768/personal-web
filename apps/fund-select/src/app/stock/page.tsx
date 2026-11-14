/**
 * 股基主页（/funds/stock）：来源分段 = 市场 | 三分法（11-15-source-segmented）
 * - market：akshare 子类圈定（默认浏览态，此时展示市场类型多选）
 * - curated：funds_stock.yaml 名单（原「股基·雪球三分法」tab）
 *
 * 为什么没有「全部」：股基三分法 142 只**全部**含在市场 universe 内，
 * 「全部」与「市场」逐只同集（已按 code 集合核对），多一个分段只是噪音。
 * 三分法成员在「市场」态用行内徽章标出。
 *
 * 复用：
 *   - FundsHeader（nav 收敛后 5 tab）
 *   - FilterPanel / FilterSheet（5 维度筛选：四维 + 夏普）
 *   - FilterChipBar / FundTable / CompareDrawer / CompareFloatingBar
 * 差异：
 *   - 默认值 STOCK_DEFAULT_FILTERS（3 / 5 / 30 / 5 / 夏普 0.8）
 *   - 调 stockApi（/api/funds/stock/*）
 */
'use client';

import { Suspense, useMemo, useState, useEffect, useRef } from 'react';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel, STOCK_DIMENSIONS } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { FundTable } from '@/components/FundTable';
import { Pagination } from '@/components/Pagination';
import { RowDetailDrawer } from '@/components/RowDetailDrawer';
import { SourceSegmented } from '@/components/SourceSegmented';
import { useCompare, useFeeDetails, useStockFundList } from '@/lib/hooks';
import {
  feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions,
} from '@/lib/compareDimensions';
import { useSearchParams } from 'next/navigation';

import { useFilters } from '@/lib/useFilters';
import {
  STOCK_DEFAULT_FILTERS, STOCK_MARKET_TYPE_OPTIONS, STOCK_OPTION_LABELS, type FundListItem,
} from '@/lib/types';

/** 股基来源分段只有两态（没有「全部」：与「市场」逐只同集） */
const STOCK_SOURCE_SEGMENTS = [
  { key: 'market' as const, label: '市场', title: 'akshare 市场子类圈定（全量）' },
  { key: 'curated' as const, label: '三分法', title: '仅雪球三分法名单（142 只）' },
];

function StockFundsPageInner() {
  const {
    filters, setFilter, setSearchCode, toggleSort, clearAll, setPage, setLimit, activeCount,
  } = useFilters(STOCK_DEFAULT_FILTERS);
  const { items, total, loading, error, reload } = useStockFundList(filters);
  const source = filters.source ?? 'market';
  const compare = useCompare<FundListItem>(5);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detailFund, setDetailFund] = useState<FundListItem | null>(null);
  // 双向闭环落点：经理页徽章 ?code=XXXX 直达，抽屉内按 code 拉完整详情
  const codeParam = useSearchParams().get('code');
  const [stubCode, setStubCode] = useState<string | null>(null);
  const searchCode = filters.search_code ?? null;
  // 处理过的 code 记录：避免清筛选触发重渲染后重复处理同一个 code
  const handledCodeRef = useRef<string | null>(null);
  useEffect(() => {
    if (!codeParam || handledCodeRef.current === codeParam) return;
    handledCodeRef.current = codeParam;
    setStubCode(codeParam);

    // ?code= 直达（经理页徽章等）：开抽屉 + 只清参数，不动筛选。
    // 11-16 起 header 代码搜索改用 ?search_code=（列表出结果，不再走这里），
    // 因此原来的 focus=1 分支已删除。
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    window.history.replaceState(null, '', url.toString());
  }, [codeParam]);

  const compareDimensions = useMemo(
    () => [...fundCompareDimensions, ...fundDisplayOnlyDimensions, ...feeDetailDimensions],
    []
  );
  const selectedWithFees = useFeeDetails(compare.selected, compare.isDrawerOpen);

  return (
    <main className="min-h-screen pb-20">
      <FundsHeader
        active="stock"
        titleOverride="股基"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        exportKind="stock"
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
          <SourceSegmented
            value={source}
            onChange={next => setFilter('source', next)}
            segments={STOCK_SOURCE_SEGMENTS}
          />
        </div>
        <FilterChipBar
          filters={filters}
          onRemove={(key, value) => {
            if (key === 'exclude_qdii') setFilter(key, false);
            else if (key === 'market_types' && value != null) {
              // 只移除这一个类型（不是整组清空）
              const rest = (filters.market_types ?? []).filter(t => t !== value);
              setFilter('market_types', rest.length > 0 ? rest : null);
            } else setFilter(key, null);
          }}
          showCodeSearch
          searchCode={searchCode}
          onClearSearch={() => setSearchCode(null)}
          marketTypeLabels={STOCK_OPTION_LABELS}
        />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={filters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
              dimensions={STOCK_DIMENSIONS}
              showMarketTypes={source === 'market'}
              marketTypeOptions={STOCK_MARKET_TYPE_OPTIONS}
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
              showRiskColumns
              marketKind="stock"
              showCuratedBadge={source === 'market'}
              onRowClick={setDetailFund}
              ddBarCapPct={60}
              trendEnabled
              highlightCode={searchCode}
              emptyHint={
                searchCode
                  ? `代码 ${searchCode} 不在基金库中。点上方「代码搜索」的 × 可回到筛选列表。`
                  : undefined
              }
            />
            {/* 搜索态只有 1 行，翻页器没有意义 */}
            {!searchCode && (
              <Pagination
                page={filters.page}
                limit={filters.limit}
                total={total}
                onPageChange={setPage}
                onLimitChange={setLimit}
              />
            )}
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
        dimensions={STOCK_DIMENSIONS}
        showMarketTypes={source === 'market'}
        marketTypeOptions={STOCK_MARKET_TYPE_OPTIONS}
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

      <RowDetailDrawer
        stub={stubCode}
        fund={detailFund}
        onClose={() => {
          // stub 模式（?code= 直达 / 代码搜索）下 detailFund 恒为 null，
          // 只清 detailFund 会导致抽屉关不掉 —— 两个都要清。
          setStubCode(null);
          setDetailFund(null);
        }}
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
