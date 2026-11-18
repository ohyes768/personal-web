/**
 * 债基主页（/funds/bond）：来源分段 = 市场 | 三分法（11-15-source-segmented）
 * - market：akshare 债基子类圈定（9782 只，此时展示市场类型多选）
 * - curated：雪球三分法 yaml 名单（31 只，债基默认分段）
 *
 * 为什么没有「全部」：债基三分法里有 3 只 akshare 记成「混合型-灵活 / QDII-FOF」的
 * 固收+（001756 / 004010 / 017970），它们不在债基市场子类内 → 「全部」不是「市场」的
 * 超集，而是「三分法 ∪ 市场」。但改两态后它们**不会消失**：它们在债基「三分法」里
 * （那是用户手工精选的名单），也在股基「市场」里（akshare 把它们记成混合型）。
 * 默认落在「三分法」：改分段前后首屏行集逐行相同（默认筛选下 all ≡ curated = 13 行）。
 */
'use client';

import { Suspense, useMemo, useState, useEffect, useRef } from 'react';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { FundTable } from '@/components/FundTable';
import { Pagination } from '@/components/Pagination';
import { RowDetailDrawerBond } from '@/components/RowDetailDrawerBond';
import { SourceSegmented } from '@/components/SourceSegmented';
import { useCompare, useFeeDetails, useFundList } from '@/lib/hooks';
import {
  feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions,
} from '@/lib/compareDimensions';
import { useSearchParams } from 'next/navigation';

import { useFilters } from '@/lib/useFilters';
import {
  BOND_MARKET_TYPE_OPTIONS, BOND_OPTION_LABELS,
  DEFAULT_FULL_REFRESH_FILTERS_BOND, type FullRefreshFilters, type FundListItem,
} from '@/lib/types';

/** 债基来源分段只有两态（「全部」已下线：默认筛选下与「三分法」逐行同集，见文件头注释） */
const BOND_SOURCE_SEGMENTS = [
  { key: 'market' as const, label: '市场', title: 'akshare 债基子类圈定（全量）' },
  { key: 'curated' as const, label: '三分法', title: '仅雪球三分法名单（31 只）' },
];

function FundsPageInner() {
  const {
    filters, setFilter, setSearchCode, toggleSort, clearAll, setPage, setLimit, activeCount,
  } = useFilters();
  const { items, total, loading, error, reload } = useFundList(filters);
  const source = filters.source ?? 'curated';
  const compare = useCompare<FundListItem>(5);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detailFund, setDetailFund] = useState<FundListItem | null>(null);
  // 全量刷新的预筛参数（11-14 修复：合并页丢了这两个 prop，按钮整个不渲染）。
  // 只作为「全量刷新」弹框的初始值，不锁定页面筛选（合并页支持自由筛选）。
  const [preFilters, setPreFilters] = useState<FullRefreshFilters>(
    DEFAULT_FULL_REFRESH_FILTERS_BOND
  );
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
        active="bond"
        titleOverride="债基"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        exportKind="bond"
        onFullRefreshComplete={pf => setPreFilters(pf)}
        preFilters={preFilters}
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
          <SourceSegmented
            value={source}
            onChange={next => setFilter('source', next)}
            segments={BOND_SOURCE_SEGMENTS}
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
          marketTypeLabels={BOND_OPTION_LABELS}
        />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={filters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
              showMarketTypes={source === 'market'}
              marketTypeOptions={BOND_MARKET_TYPE_OPTIONS}
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
              marketKind="bond"
              showCuratedBadge={source === 'market'}
              onRowClick={setDetailFund}
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
        showMarketTypes={source === 'market'}
        marketTypeOptions={BOND_MARKET_TYPE_OPTIONS}
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

export default function FundsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <FundsPageInner />
    </Suspense>
  );
}
