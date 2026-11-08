/**
 * 夏普榜单独立 Tab（/funds/sharpe-board，只读页面）
 *
 * - 顶部：导航（FundsNavigation 五 Tab）+ 定时任务齿轮（SchedulerDialog 复用，
 *   「立即执行」补本周；展示筛选绝不触发采集）
 * - 入选规则只读说明 + 最新榜日期/采集状态；展示筛选；总图（全量命中基金）；
 *   分页列表（翻页不重置图与筛选状态；展示筛选变化重置列表页到第 1 页）
 * - source 切换用 AbortController 中止旧请求，防旧来源响应覆盖新来源状态
 * - 图表 dynamic(ssr:false) 加载 echarts，仅本页使用
 */
'use client';

import { Cog6ToothIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import dynamic from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';

import { FundsNavigation } from '@/components/FundsNavigation';
import { Pagination } from '@/components/Pagination';
import { RowDetailDrawer } from '@/components/RowDetailDrawer';
import { SchedulerDialog } from '@/components/SchedulerDialog';
import { SharpeBoardFilters } from '@/components/sharpe-board/SharpeBoardFilters';
import { SharpeBoardProfileCard } from '@/components/sharpe-board/SharpeBoardProfileCard';
import { SharpeBoardEmptyCard, SharpeBoardStatusBar } from '@/components/sharpe-board/SharpeBoardStatus';
import { SharpeBoardTable } from '@/components/sharpe-board/SharpeBoardTable';
import {
  classifySharpeBoard,
  fetchSharpeBoard,
  hasPointInRange,
  parseSharpeFiltersFromSearch,
  sharpeFiltersActive,
  sharpeFiltersToSearch,
  type SharpeBoardFilters as Filters,
  type SharpeBoardResponse,
} from '@/lib/sharpe-board';
import type { FundListItem } from '@/lib/types';

const SharpeChart = dynamic(() => import('@/components/sharpe-board/SharpeChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] flex items-center justify-center text-sm text-ink-muted" aria-label="图表加载中">
      图表加载中…
    </div>
  ),
});

function SharpeBoardPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseSharpeFiltersFromSearch(searchParams), [searchParams]);

  const [data, setData] = useState<SharpeBoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [hiddenCodes, setHiddenCodes] = useState<ReadonlySet<string>>(new Set());
  const [focusCode, setFocusCode] = useState<string | null>(null);
  const [schedulerOpen, setSchedulerOpen] = useState(searchParams.get('scheduler') === '1');
  // 详情抽屉：榜单行只有 code/name，传 stub，抽屉内部按 code 拉完整详情
  const [detailFund, setDetailFund] = useState<FundListItem | null>(null);
  const openDetail = useCallback((code: string, name: string) => {
    setDetailFund({
      code, name, fund_type: '', market_subtype: '',
      size_yi: null, age_years: null, dd_3y: null,
      ret_1m: null, ret_1y: null, ret_3y: null, ret_5y: null,
      sharpe: null, ir: null, alpha: null, gamma: null, alpha_ir: null, excess_3y: null,
      mgr_name: null, mgr_company: null, mgr_experience_years: null,
      rate_bond_pct: null, fee_mgmt: null, fee_custody: null, fee_service: null, fee_annual: null,
      updated_at: null, rank_ytd: null, rank_1y: null, rank_3y: null, rank_5y: null,
    });
  }, []);

  // 拉取榜单：AbortController 中止旧请求（source 快速切换不串台）
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchSharpeBoard(filters, controller.signal)
      .then(res => {
        if (controller.signal.aborted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : '请求失败，请重试');
        setLoading(false);
      });
    return () => controller.abort();
  }, [filters, reloadTick]);

  // 来源切换/URL 直改：清空图例隐藏与聚焦（不同来源基金集合不同）
  useEffect(() => {
    setHiddenCodes(new Set());
    setFocusCode(null);
  }, [filters.source]);

  /** 筛选更新 → URL（push 可回退）。命中集变化的筛选重置 page=1；
   *  range 只裁图不改命中集，保持 page。 */
  const updateFilters = useCallback(
    (patch: Partial<Filters>) => {
      const next: Filters = { ...filters, ...patch };
      const pageAffecting =
        'source' in patch || 'minLatestSharpe' in patch || 'minWeeks' in patch || 'latestOnly' in patch;
      if (pageAffecting) next.page = 1;
      const qs = sharpeFiltersToSearch(next).toString();
      router.push(qs ? `?${qs}` : '?', { scroll: false });
    },
    [filters, router],
  );

  const setPage = useCallback(
    (page: number) => updateFilters({ page: Math.max(1, Math.floor(page)) }),
    [updateFilters],
  );
  const setLimit = useCallback(
    (limit: number) => updateFilters({ limit, page: 1 }),
    [updateFilters],
  );

  // echarts 图例切换回传：不可见的 code 进 hiddenCodes（React 单一真相源）
  const onLegendChange = useCallback((visibleByCode: Record<string, boolean>) => {
    setHiddenCodes(
      new Set(Object.entries(visibleByCode).filter(([, visible]) => !visible).map(([code]) => code)),
    );
  }, []);

  const onFocusToggle = useCallback((code: string) => {
    setFocusCode(prev => (prev === code ? null : code));
  }, []);

  const restoreAll = useCallback(() => {
    setHiddenCodes(new Set());
    setFocusCode(null);
  }, []);

  const clearDisplayFilters = useCallback(() => {
    updateFilters({ minLatestSharpe: null, minWeeks: 1, latestOnly: false });
  }, [updateFilters]);

  // 聚焦 = 除目标外全部隐藏（与图例隐藏合并为 effectiveHidden）
  const effectiveHidden = useMemo(() => {
    const merged = new Set(hiddenCodes);
    if (focusCode !== null) {
      for (const s of data?.series ?? []) {
        if (s.code !== focusCode) merged.add(s.code);
      }
    }
    return merged;
  }, [hiddenCodes, focusCode, data]);

  const phase = data ? classifySharpeBoard(data, sharpeFiltersActive(filters)) : null;
  const rangeHasPoint = data ? hasPointInRange(data.series) : false;
  const hasActiveView = hiddenCodes.size > 0 || focusCode !== null;

  return (
    <main className="min-h-screen pb-20">
      <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <a
              href="/"
              className="text-xs text-ink-muted hover:text-ink-strong transition-colors"
            >
              ← 返回首页
            </a>
            <div className="flex items-baseline gap-3 mt-0.5 flex-wrap">
              <h1 className="text-lg font-semibold text-ink-strong">夏普榜单</h1>
              <FundsNavigation active="sharpe-board" />
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {data && (
              <span className="hidden sm:inline text-sm text-ink-muted">
                命中 <span className="tnum font-semibold text-ink-strong">{data.total}</span> 只
              </span>
            )}
            <button
              type="button"
              onClick={() => setSchedulerOpen(true)}
              aria-label="定时任务"
              title="定时任务（立即执行可补本周榜单）"
              aria-haspopup="dialog"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-paper-deep hover:text-info focus-visible:outline-2 focus-visible:outline-info"
            >
              <Cog6ToothIcon aria-hidden="true" className="h-5 w-5" />
            </button>
          </div>
        </div>
        {schedulerOpen && <SchedulerDialog onClose={() => setSchedulerOpen(false)} />}
      </header>

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4 space-y-3">
        {data && <SharpeBoardProfileCard profile={data.profile} />}
        {data && <SharpeBoardStatusBar data={data} />}

        <SharpeBoardFilters filters={filters} onChange={updateFilters} />

        {/* 总图区 */}
        <section aria-label="夏普曲线总图" className="bg-paper-card rounded-lg border border-rule">
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-3">
            <h2 className="text-sm font-medium text-ink-strong">
              夏普曲线
              <span className="ml-2 text-xs font-normal text-ink-muted">
                全部命中基金（不随列表分页截断）· 缺席周断线留空 · 单点可见
              </span>
            </h2>
            {hasActiveView && (
              <button
                type="button"
                onClick={restoreAll}
                className="px-2.5 py-1 rounded-lg bg-paper-deep text-xs text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
              >
                恢复全部（{hiddenCodes.size > 0 ? `隐藏 ${hiddenCodes.size} 只` : ''}
                {focusCode !== null ? `${hiddenCodes.size > 0 ? ' · ' : ''}聚焦中` : ''}）
              </button>
            )}
          </div>
          <div className="px-3 pb-3">
            {loading && !data && (
              <div className="h-[420px] animate-pulse" aria-label="加载中">
                <div className="h-full bg-paper-tint rounded" />
              </div>
            )}
            {error && (
              <div className="h-[420px] flex flex-col items-center justify-center gap-3">
                <p className="text-sm text-down">加载失败：{error}</p>
                <button
                  type="button"
                  onClick={() => setReloadTick(t => t + 1)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-paper-deep text-sm text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
                >
                  <ArrowPathIcon aria-hidden="true" className="h-4 w-4" />
                  重试
                </button>
              </div>
            )}
            {!error && data && phase === 'ok' && !rangeHasPoint && (
              <div className="h-[420px] flex flex-col items-center justify-center gap-2 text-ink-muted">
                <p className="text-sm">所选时间范围内无数据点</p>
                <p className="text-xs">范围只裁图；列表仍按全历史统计，切换「全部」可看到完整曲线。</p>
              </div>
            )}
            {!error && data && phase === 'ok' && rangeHasPoint && (
              <SharpeChart
                weeks={data.weeks}
                series={data.series}
                minLatestSharpe={filters.minLatestSharpe}
                hiddenCodes={effectiveHidden}
                onLegendChange={onLegendChange}
              />
            )}
          </div>
        </section>

        {/* 列表区 */}
        <section aria-label="在榜基金列表" className="bg-paper-card rounded-lg border border-rule">
          {error && (
            <div className="p-8 text-center">
              <p className="text-down mb-3 text-sm">加载失败：{error}</p>
              <button
                type="button"
                onClick={() => setReloadTick(t => t + 1)}
                className="px-3 py-1.5 rounded-lg bg-paper-deep text-sm text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
              >
                重试
              </button>
            </div>
          )}
          {!error && data && phase !== null && phase !== 'ok' && (
            <SharpeBoardEmptyCard phase={phase} data={data} onClearFilters={clearDisplayFilters} />
          )}
          {!error && data && (
            <>
              <SharpeBoardTable
                items={data.items}
                loading={loading}
                focusCode={focusCode}
                onFocusToggle={onFocusToggle}
                onOpenDetail={openDetail}
              />
              {phase === 'ok' && (
                <Pagination
                  page={filters.page}
                  limit={filters.limit}
                  total={data.total}
                  onPageChange={setPage}
                  onLimitChange={setLimit}
                />
              )}
            </>
          )}
        </section>

        <RowDetailDrawer fund={detailFund} onClose={() => setDetailFund(null)} />
      </div>
    </main>
  );
}

export default function SharpeBoardPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <SharpeBoardPageInner />
    </Suspense>
  );
}
