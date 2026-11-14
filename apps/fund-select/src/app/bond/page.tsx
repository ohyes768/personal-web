/**
 * 债基主页（/funds/bond）：来源分段 = 全部 | 三分法 | 市场（11-15-source-segmented）
 * - curated：雪球三分法 yaml 名单（原「债基·雪球三分法」tab）
 * - market：akshare 子类圈定（原「债基·市场」tab，此时展示市场类型多选）
 * - all：两者并集（默认浏览态）
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
import { useRouter, useSearchParams } from 'next/navigation';

import { useFilters } from '@/lib/useFilters';
import type { FundListItem } from '@/lib/types';

function FundsPageInner() {
  const { filters, setFilter, toggleSort, clearAll, setPage, setLimit, activeCount } = useFilters();
  const { items, total, loading, error, reload } = useFundList(filters);
  const source = filters.source ?? 'all';
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
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
          <SourceSegmented
            value={source}
            onChange={next => setFilter('source', next)}
          />
        </div>
        <FilterChipBar
          filters={filters}
          onRemove={key => setFilter(key, key === 'exclude_qdii' ? false : null)}
          showCodeSearch
        />
        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">
            <FilterPanel
              filters={filters}
              onChange={(key, v) => setFilter(key, v)}
              onClearAll={clearAll}
              activeCount={activeCount}
              showMarketTypes={source === 'market'}
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
              onRowClick={setDetailFund}
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
        filters={filters}
        onChange={(key, v) => setFilter(key, v)}
        onClearAll={clearAll}
        activeCount={activeCount}
        showMarketTypes={source === 'market'}
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
