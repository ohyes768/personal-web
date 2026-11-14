/**
 * 股基·市场 tab 主页（/funds/discovery-stock）
 *
 * 与股票 tab（/funds/stock）平列，复用 FundsHeader / FilterPanel / FundTable / CompareDrawer 等；
 * 差异：
 *   - 默认值 DISCOVERY_STOCK_DEFAULT_FILTERS（含默认 market_types = ['股票型','指数型','混合型','QDII']）
 *   - 调 discoveryStockApi（/api/funds/discovery-stock/*）
 *   - 筛选面板多一栏「基金类型」多选
 *   - 「全量刷新」按钮：触发 4 阶段流水线（rankhandler + fund_basic + 日频净值 + 风险指标），
 *     完成后把预筛选值同步到左侧面板（disabled 不可改）
 */
'use client';

import { Suspense, useCallback, useMemo, useState, useEffect, useRef } from 'react';

import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterPanel, STOCK_DIMENSIONS } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { FundTable } from '@/components/FundTable';
import { Pagination } from '@/components/Pagination';
import { RowDetailDrawer } from '@/components/RowDetailDrawer';
import { useCompare, useDiscoveryStockFundList, useFeeDetails } from '@/lib/hooks';
import { feeDetailDimensions, fundCompareDimensions, fundDisplayOnlyDimensions } from '@/lib/compareDimensions';
import { useRouter, useSearchParams } from 'next/navigation';

import { useFilters } from '@/lib/useFilters';
import {
  DEFAULT_FULL_REFRESH_FILTERS_STOCK,
  DISCOVERY_STOCK_DEFAULT_FILTERS,
  STOCK_MARKET_TYPE_OPTIONS,
  type FullRefreshFilters,
  type FundListItem,
} from '@/lib/types';

/** 全量 refresh 完成后，左侧筛选面板锁定的 3 个预筛字段 */
const LOCKED_PRE_FILTERS = ['min_ret_3y', 'min_size_yi', 'min_mgr_exp'];

function DiscoveryStockPageInner() {
  const { filters, setFilter, toggleSort, clearAll, setPage, setLimit, activeCount } = useFilters(DISCOVERY_STOCK_DEFAULT_FILTERS);
  const { items, total, loading, error, reload } = useDiscoveryStockFundList(filters);
  const compare = useCompare<FundListItem>(5);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detailFund, setDetailFund] = useState<FundListItem | null>(null);
  // 双向闭环落点：经理页徽章 ?code=XXXX 直达，抽屉内按 code 拉完整详情
  const codeParam = useSearchParams().get('code');
  const [stubCode, setStubCode] = useState<string | null>(null);
  const focusParam = useSearchParams().get('focus');
  const router = useRouter();
  // 处理过的 code 记录：避免清筛选触发重渲染后重复处理同一个 code
  const handledCodeRef = useRef<string | null>(null);
  useEffect(() => {
    if (!codeParam || handledCodeRef.current === codeParam) return;
    handledCodeRef.current = codeParam;
    setStubCode(codeParam);

    if (focusParam === '1') {
      // 来自 header 代码搜索：一次导航同时完成「清筛选 + 去掉 code/focus」。
      // 不能先 clearAll() 再 replaceState —— 两次导航会互相覆盖，
      // 实测结果是筛选没被清掉、目标基金仍在列表外。
      // 同时也绕开 discovery-* 页的 preFilters 锁定字段（clearAll 清不到它们）。
      // ⚠ 只推 query（'?cleared=1'），绝不拼 url.pathname：
      // pathname 已含 basePath /funds，再拼会变成 /funds/funds/... 404（契约 §4）。
      router.push('?cleared=1', { scroll: false });
      return;
    }

    // 普通 ?code= 直达（经理页徽章等）：只清参数，不动筛选
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    window.history.replaceState(null, '', url.toString());
  }, [codeParam, focusParam, router]);

  // 预筛选值（来自全量 refresh 完成时回写；lockedFields 在左侧 disabled）
  const [preFilters, setPreFilters] = useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS_STOCK);

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
        active="discovery-stock"
        total={total}
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={reload}
        exportKind="discovery-stock"
        onFullRefreshComplete={handleFullRefreshComplete}
        preFilters={preFilters}
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <FilterChipBar filters={effectiveFilters} onRemove={handleRemove} showCodeSearch />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={effectiveFilters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
              dimensions={STOCK_DIMENSIONS}
              showMarketTypes
              marketTypeOptions={STOCK_MARKET_TYPE_OPTIONS}
              lockedFields={LOCKED_PRE_FILTERS}
              hideExcludeQdii
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
              onRowClick={setDetailFund}
              ddBarCapPct={60}
              marketKind="stock"
              trendEnabled
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
        dimensions={STOCK_DIMENSIONS}
        showMarketTypes
        marketTypeOptions={STOCK_MARKET_TYPE_OPTIONS}
        lockedFields={LOCKED_PRE_FILTERS}
        hideExcludeQdii
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

export default function DiscoveryStockPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <DiscoveryStockPageInner />
    </Suspense>
  );
}
