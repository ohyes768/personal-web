/**
 * 经理维度 Tab（/funds/managers，任务 11-10-fund-manager-evaluation）
 *
 * 以经理为主体的列表：从业年限 / 加权年化 / 回撤 / 规模筛选 + 排序 + 分页。
 * 点击行展开历任基金（含已离任，按需拉取 /managers/{id}）。
 *
 * 视觉契约（任务 11-11-fund-manager-tab-refresh）：与另外 5 个 tab 统一——
 *   FundsHeader（返回首页 / 标题 / 导航 / 总数 / 刷新 / 齿轮）
 *   + FilterPanelShell/DimensionControl（桌面左栏、窄屏 sheet 同一套表单）
 *   + FilterChipBar 语义的激活条件 chips + SortableHeader 三态排序图标
 * 不自己写 header、不写顶部内联筛选行、不用文字箭头排序。
 */
'use client';

import { ArrowPathIcon, FunnelIcon, XMarkIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { FilterPanelShell, DimensionControl, type Dimension } from '@/components/FilterSidebar';
import { FundsHeader } from '@/components/FundsHeader';
import { Pagination } from '@/components/Pagination';
import { SortableHeader } from '@/components/SortableHeader';
import { RankInline } from '@/lib/rankColor';
import {
  MANAGER_DEFAULT_FILTERS,
  managerApi,
  type ManagerDetail,
  type ManagerFilters,
  type ManagerListItem,
  type ManagerScreenResponse,
  type TenureAffiliation,
} from '@/lib/managers';

const fmtPct = (v: number | null, digits = 1) =>
  v != null ? `${v.toFixed(digits)}%` : '-';
const fmtNum = (v: number | null, digits = 1) => (v != null ? v.toFixed(digits) : '-');

/** 收益率：带正负号（与股票 tab FundTable 的 fmtRet 同格式） */
const fmtRet = (v: number | null | undefined): string => {
  if (v == null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

/** 收益率配色：涨绿跌灰（与股票 tab FundTable 的 retColor 同规则） */
const retColor = (v: number | null | undefined): string => {
  if (v == null) return 'text-ink-soft';
  return v >= 0 ? 'text-up' : 'text-down';
};

/** 经理筛选维度：键与后端 query 参数同名，DropdownControl 直接按 key 取值 */
const MANAGER_DIMENSIONS: Dimension[] = [
  { key: 'min_career_years', label: '从业年限', unit: '年', min: 0, max: 40, step: 1 },
  { key: 'min_weighted_annual', label: '加权年化', unit: '%', min: -20, max: 50, step: 1 },
  { key: 'max_drawdown', label: '最大回撤', unit: '%', min: 0, max: 100, step: 5 },
  { key: 'min_scale_yi', label: '在管规模', unit: '亿', min: 0, max: 2000, step: 10 },
  { key: 'min_win_rate', label: '任期胜率', unit: '%', min: 0, max: 100, step: 10 },
  { key: 'min_solo_ratio', label: '独管比例', unit: '%', min: 0, max: 100, step: 10 },
  { key: 'max_fund_count', label: '在管只数', unit: '只', min: 1, max: 50, step: 1 },
];

type NumericKey =
  | 'min_career_years' | 'min_weighted_annual' | 'max_drawdown' | 'min_scale_yi'
  | 'min_win_rate' | 'min_solo_ratio' | 'max_fund_count';
const NUMERIC_KEYS: NumericKey[] = [
  'min_career_years', 'min_weighted_annual', 'max_drawdown', 'min_scale_yi',
  'min_win_rate', 'min_solo_ratio', 'max_fund_count',
];

/** chip 文案：与基金 tab 的 FilterChipBar 同构（label + 关系符 + 值） */
const CHIP_LABELS: Record<NumericKey, { label: string; fmt: (v: number) => string }> = {
  min_career_years: { label: '从业年限', fmt: v => `≥ ${v} 年` },
  min_weighted_annual: { label: '加权年化', fmt: v => `≥ ${v}%` },
  max_drawdown: { label: '最大回撤', fmt: v => `≤ ${v}%` },
  min_scale_yi: { label: '在管规模', fmt: v => `≥ ${v} 亿` },
  min_win_rate: { label: '任期胜率', fmt: v => `≥ ${v}%` },
  min_solo_ratio: { label: '独管比例', fmt: v => `≥ ${v}%` },
  max_fund_count: { label: '在管只数', fmt: v => `≤ ${v} 只` },
};

function ManagersPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<ManagerFilters>(() => {
    // 第 3 层落点：基金详情抽屉 ?keyword=经理名 跳转过来直接出结果
    const kw = searchParams.get('keyword');
    return kw ? { ...MANAGER_DEFAULT_FILTERS, keyword: kw } : MANAGER_DEFAULT_FILTERS;
  });
  const [data, setData] = useState<ManagerScreenResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  // 展开的经理详情（按需拉取）
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ManagerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const setFilter = useCallback(<K extends keyof ManagerFilters>(key: K, value: ManagerFilters[K]) => {
    setFilters(prev => ({ ...prev, [key]: value, page: 1 }));
  }, []);

  /** 三态排序：同列再点切方向（与基金表 SortableHeader 行为一致） */
  const toggleSort = useCallback((field: string) => {
    setFilters(prev => prev.sort === field
      ? { ...prev, order: prev.order === 'desc' ? 'asc' : 'desc', page: 1 }
      : { ...prev, sort: field, order: 'desc', page: 1 });
  }, []);

  const clearAll = useCallback(() => {
    setFilters(prev => ({ ...MANAGER_DEFAULT_FILTERS, sort: prev.sort, order: prev.order }));
  }, []);

  const activeCount = useMemo(
    () => NUMERIC_KEYS.filter(k => filters[k] != null).length + (filters.keyword ? 1 : 0),
    [filters],
  );

  const load = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    managerApi.screen(filters, controller.signal)
      .then(setData)
      .catch((e: unknown) => {
        if ((e as Error).name === 'AbortError') return;
        setError((e as Error).message || '加载失败');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const toggleExpand = useCallback((managerId: string) => {
    if (expandedId === managerId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(managerId);
    setDetail(null);
    setDetailLoading(true);
    managerApi.getDetail(managerId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [expandedId]);

  const panel = (
    <FilterPanelShell onClearAll={clearAll} activeCount={activeCount}>
      {MANAGER_DIMENSIONS.map(dim => (
        <DimensionControl
          key={dim.key}
          dim={dim}
          value={filters[dim.key as NumericKey]}
          onChange={v => setFilter(dim.key as NumericKey, v)}
        />
      ))}
    </FilterPanelShell>
  );

  return (
    <main className="min-h-screen pb-20">
      <FundsHeader
        active="managers"
        total={data?.total ?? 0}
        totalUnit="人"
        activeFilterCount={activeCount}
        onOpenMobileFilter={() => setSheetOpen(true)}
        onRefreshed={load}
        exportKind="managers"
      />

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4">
        {/* 激活条件 chips（与基金 tab 的 FilterChipBar 同构）+ 关键词输入 */}
        <div className="flex items-center gap-2 flex-wrap py-1.5">
          {activeCount === 0 ? (
            <span className="flex items-center gap-1.5 text-xs text-ink-soft">
              <FunnelIcon className="w-3.5 h-3.5" />
              未筛选
            </span>
          ) : (
            <>
              {NUMERIC_KEYS.filter(k => filters[k] != null).map(key => {
                const v = filters[key] as number;
                const meta = CHIP_LABELS[key];
                return (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info"
                  >
                    {meta.label} {meta.fmt(v)}
                    <button
                      onClick={() => setFilter(key, null)}
                      className="hover:text-down"
                      aria-label={`移除${meta.label}筛选`}
                    >
                      <XMarkIcon className="w-3 h-3" />
                    </button>
                  </span>
                );
              })}
              {filters.keyword && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info">
                  姓名/公司: {filters.keyword}
                  <button
                    onClick={() => setFilter('keyword', null)}
                    className="hover:text-down"
                    aria-label="移除关键词筛选"
                  >
                    <XMarkIcon className="w-3 h-3" />
                  </button>
                </span>
              )}
            </>
          )}
          {/* 关键词是自由文本，面板里放不下输入框，独占这一行右侧 */}
          <input
            value={filters.keyword ?? ''}
            onChange={e => setFilter('keyword', e.target.value || null)}
            placeholder="搜索姓名 / 公司"
            aria-label="搜索经理姓名或公司"
            className="ml-auto w-40 px-2 py-0.5 text-xs border border-rule rounded bg-paper-card text-ink-strong focus:outline-none focus:border-info"
          />
        </div>

        {error && (
          <div className="mb-3 text-sm text-down" role="alert">{error}</div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[10.5rem_minmax(0,1fr)] gap-3 items-start">
          <aside className="hidden lg:block sticky top-16">{panel}</aside>

          <section className="min-w-0 overflow-x-auto bg-paper-card rounded-lg border border-rule">
            <table className="w-full table-fixed text-xs">
              <thead className="border-b border-rule-strong">
                <tr>
                  <SortableHeader label="经理" field="name" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} align="left" className="w-[7rem] min-w-[7rem]" />
                  <th className="px-1.5 py-2 text-left text-xs font-medium text-ink-muted w-[7rem] min-w-[7rem]">公司</th>
                  <SortableHeader label="从业" field="career_years" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} />
                  <SortableHeader label="年化·含离任" field="weighted_annual" className="w-[5.5rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} tip="全部任期（含已离任）的时长加权年化：职业生涯整体口径" />
                  <SortableHeader label="在管年化" field="current_weighted_annual" className="w-[5.5rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} tip="仅当前在管的主动权益段时长加权：当下状态口径。无在管段显示 -" />
                  <SortableHeader label="胜率" field="tenure_win_rate" className="w-[4rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} tip="任期胜率：任职回报为正的任期占比。中位数约 55%，≥2/3 显著优于平均" />
                  <SortableHeader label="独管" field="solo_ratio" className="w-[4rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} tip="独管比例：在管基金中仅自己一位经理的占比。共管多 → 贡献难归因（挂名风险）" />
                  <SortableHeader label="最长任期" field="longest_tenure_years" className="w-[4.5rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} />
                  <SortableHeader label="回撤" field="max_drawdown" className="w-[4.5rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} />
                  <SortableHeader label="夏普" field="sharpe" className="w-[4rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} />
                  <SortableHeader label="规模" field="current_scale_yi" className="w-[4.5rem]" currentSort={filters.sort} currentOrder={filters.order} onSort={toggleSort} />
                  <th className="px-1.5 py-2 text-right text-xs font-medium text-ink-muted w-[5.5rem]">在管</th>
                </tr>
              </thead>
              <tbody>
                {loading && !data && (
                  <tr>
                    <td colSpan={12} className="p-8">
                      <div className="space-y-2 animate-pulse" aria-label="加载中">
                        {Array.from({ length: 6 }).map((_, i) => (
                          <div key={i} className="h-8 bg-paper-tint rounded" />
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
                {!loading && data && data.items.length === 0 && (
                  <tr>
                    <td colSpan={12} className="p-12 text-center text-ink-muted">
                      暂无数据，请调整筛选条件
                    </td>
                  </tr>
                )}
                {(data?.items ?? []).map(m => (
                  <ManagerRow
                    key={m.manager_id}
                    manager={m}
                    expanded={expandedId === m.manager_id}
                    detail={expandedId === m.manager_id ? detail : null}
                    detailLoading={expandedId === m.manager_id && detailLoading}
                    onToggle={() => toggleExpand(m.manager_id)}
                  />
                ))}
              </tbody>
            </table>

            <Pagination
              page={filters.page}
              limit={filters.limit}
              total={data?.total ?? 0}
              onPageChange={p => setFilters(prev => ({ ...prev, page: p }))}
              onLimitChange={n => setFilters(prev => ({ ...prev, limit: n, page: 1 }))}
            />
          </section>
        </div>

        <p className="mt-4 text-xs text-ink-muted leading-relaxed">
          口径说明：加权年化 = 排除债基/货币/FOF 后按管理天数加权（避免经理自选代表作）；
          回撤/夏普取代表基金（主动权益优先、任期最长、在管优先）按任职窗口的复权净值计算。
          数据源：天天基金经理档案（每日非实时）。
        </p>
      </div>

      {/* 窄屏筛选 sheet：与基金 tab 的 FilterSheet 同一套表单，这里内联避免多传一层 props */}
      {sheetOpen && (
        <>
          <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={() => setSheetOpen(false)} aria-hidden="true" />
          <div
            className="fixed bottom-0 left-0 right-0 z-50 bg-paper rounded-t-2xl max-h-[80vh] overflow-y-auto lg:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="筛选条件"
          >
            <div className="sticky top-0 bg-paper px-4 py-3 flex items-center justify-between border-b border-rule">
              <span className="font-semibold text-ink-strong">筛选</span>
              <button onClick={() => setSheetOpen(false)} className="p-1 text-ink-muted hover:text-ink-strong" aria-label="关闭筛选">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
            <div className="p-3">
              {panel}
              <button
                onClick={() => setSheetOpen(false)}
                className="w-full mt-3 py-2.5 text-sm font-medium text-white bg-accent hover:bg-accent-hover rounded-lg"
              >
                查看结果
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}

/** 归属徽章：tab 跳转 + 在榜周数；无归属时退化为纯代码 */
const AFFILIATION_TABS: Record<NonNullable<TenureAffiliation['tab']>, { label: string; href: string }> = {
  'bond': { label: '债基名单', href: '/bond' },
  'stock': { label: '股基名单', href: '/stock' },
  'discovery-bond': { label: '债基·市场', href: '/discovery-bond' },
  'discovery-stock': { label: '股基·市场', href: '/discovery-stock' },
};

function AffiliationBadges({ aff, code, name }: {
  aff: TenureAffiliation | null | undefined;
  code: string;
  name: string | null;
}) {
  const tabInfo = aff?.tab ? AFFILIATION_TABS[aff.tab] : null;
  return (
    <span className="inline-flex items-center gap-1">
      {tabInfo ? (
        <Link
          href={`${tabInfo.href}?code=${code}`}
          className="inline-flex items-center rounded bg-info-tint px-1.5 py-[1px] font-mono text-[11px] text-info transition-colors hover:bg-info hover:text-white"
          title={`到${tabInfo.label}查看${name ?? code}的详情`}
        >
          {code}
        </Link>
      ) : (
        <span className="font-mono text-info">{code}</span>
      )}
      {aff && aff.board_weeks > 0 && (
        <span
          className="inline-flex items-center rounded-full bg-up-tint px-1.5 py-[1px] text-[10px] text-up"
          title="上过夏普周榜的周数（历史累计）"
        >
          在榜 {aff.board_weeks} 周
        </span>
      )}
    </span>
  );
}

function ManagerRow({ manager: m, expanded, detail, detailLoading, onToggle }: {
  manager: ManagerListItem;
  expanded: boolean;
  detail: ManagerDetail | null;
  detailLoading: boolean;
  onToggle: () => void;
}) {
  const td = 'px-1.5 py-1.5';
  // 展开详情的 tenure tab：默认在任。切换经理时组件复用，但 hidden 状态无副作用
  const [tenureTab, setTenureTab] = useState<'current' | 'past'>('current');
  const currentTenures = detail?.tenures?.filter(t => t.is_current) ?? [];
  const pastTenures = detail?.tenures?.filter(t => !t.is_current) ?? [];
  const shownTenures = tenureTab === 'current' ? currentTenures : pastTenures;
  return (
    <>
      <tr
        onClick={onToggle}
        className={`border-b border-rule cursor-pointer transition-colors hover:bg-paper-tint ${expanded ? 'bg-info-tint' : ''}`}
      >
        <td className={`${td} text-ink-strong`}>
          <div className="truncate" title={m.name}>{m.name}</div>
          {m.representative_fund && (
            <div className="text-[10px] text-ink-soft font-mono truncate">{m.representative_fund}</div>
          )}
        </td>
        <td className={`${td} text-ink-muted`}>
          <div className="truncate" title={m.company ?? ''}>{m.company ?? '-'}</div>
        </td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtNum(m.career_years)}</td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>
          <div className={`font-medium ${(m.weighted_annual ?? 0) >= 10 ? 'text-up' : (m.weighted_annual ?? 0) < 0 ? 'text-down' : ''}`}>
            {fmtPct(m.weighted_annual)}
          </div>
          {(m.rep_divergence ?? 0) > 15 && (
            <div className="text-[10px] font-normal text-star" title={`最长任期年化比整体高 ${m.rep_divergence}pp，业绩集中在单只代表作`}>
              代表作 +{m.rep_divergence}pp
            </div>
          )}
        </td>
        <td className={`${td} text-right tnum whitespace-nowrap font-medium ${(m.current_weighted_annual ?? 0) >= 10 ? 'text-up' : (m.current_weighted_annual ?? 0) < 0 ? 'text-down' : 'text-ink-muted'}`}>
          {fmtPct(m.current_weighted_annual)}
        </td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtPct(m.tenure_win_rate, 0)}</td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtPct(m.solo_ratio, 0)}</td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtNum(m.longest_tenure_years)}</td>
        <td className={`${td} text-right tnum whitespace-nowrap ${(m.max_drawdown ?? 0) <= -60 ? 'text-down' : ''}`}>
          {fmtPct(m.max_drawdown)}
        </td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtNum(m.sharpe, 2)}</td>
        <td className={`${td} text-right tnum whitespace-nowrap`}>{fmtNum(m.current_scale_yi, 0)}</td>
        <td className={`${td} text-right whitespace-nowrap`}>
          <div className="tnum text-ink-muted">
            {m.current_fund_count ?? '-'}/{m.managed_fund_count ?? '-'}
          </div>
          {m.board_on_current > 0 && (
            <div className="mt-0.5 inline-flex items-center gap-0.5 rounded-full bg-up-tint px-1.5 py-[1px] text-[10px] text-up"
                 title={`在管 ${m.current_fund_total} 只中有 ${m.board_on_current} 只上过夏普周榜`}>
              在榜 {m.board_on_current}
            </div>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-paper-tint">
          <td colSpan={12} className="px-3 py-3">
            {detailLoading ? (
              <span className="text-xs text-ink-muted inline-flex items-center gap-1">
                <ArrowPathIcon className="w-3 h-3 animate-spin" /> 加载历任基金…
              </span>
            ) : detail?.tenures?.length ? (
              <div>
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  {/* 在任 / 已离任 分 tab：默认在任（当下状态优先） */}
                  <div className="flex items-center gap-0.5" role="tablist" aria-label="历任基金分组">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tenureTab === 'current'}
                      onClick={() => setTenureTab('current')}
                      className={`px-2 py-0.5 rounded text-xs transition-colors ${
                        tenureTab === 'current' ? 'bg-accent text-white' : 'bg-paper-deep text-ink-muted hover:text-ink-strong'
                      }`}
                    >
                      在任 {currentTenures.length}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tenureTab === 'past'}
                      onClick={() => setTenureTab('past')}
                      className={`px-2 py-0.5 rounded text-xs transition-colors ${
                        tenureTab === 'past' ? 'bg-accent text-white' : 'bg-paper-deep text-ink-muted hover:text-ink-strong'
                      }`}
                    >
                      已离任 {pastTenures.length}
                    </button>
                  </div>
                  <span className="text-[11px] text-ink-muted">
                    {tenureTab === 'current'
                      ? '当前在管基金 · 在管年化按这些段加权'
                      : '已离任基金 · 计入「年化·含离任」口径'}
                  </span>
                </div>
                {/* 历任基金表：table-fixed + 显式列宽，与外层列表表同宽铺满
                    （外层 td 已是 colSpan=12 全宽）。不设列宽时内容会撑出容器
                    出现横向滚动条。 */}
                {shownTenures.length === 0 ? (
                  <span className="text-xs text-ink-muted">
                    {tenureTab === 'current' ? '无在管基金' : '无已离任基金'}
                  </span>
                ) : (
                <table className="w-full table-fixed text-xs">
                  <thead>
                    <tr className="text-left text-ink-muted border-b border-rule">
                      <th className="w-[8rem] py-1 pr-2 font-medium">代码</th>
                      <th className="w-[7rem] py-1 pr-2 font-medium">名称</th>
                      <th className="w-[5.5rem] py-1 pr-2 font-medium">类型</th>
                      <th className="w-[3.5rem] py-1 pr-2 text-right font-medium">规模(亿)</th>
                      <th className="w-[9.5rem] py-1 pr-2 font-medium">任职期间</th>
                      <th className="w-[3rem] py-1 pr-2 text-right font-medium">天数</th>
                      <th className="w-[4rem] py-1 pr-2 text-right font-medium">任职回报</th>
                      <th className="w-[3.5rem] py-1 pr-2 text-right font-medium">年化</th>
                      <th className="w-[7rem] py-1 pr-2 text-right font-medium">
                        <span
                          className="hover-tip hover-tip--wrap hover-tip--right"
                          data-tip="基金自身口径的近 1 年收益（含同类排名）。与「任职回报」不同：后者按该经理的任职窗口算——经理离任后基金可能已换人"
                        >
                          近1年
                        </span>
                      </th>
                      <th className="w-[7rem] py-1 pr-2 text-right font-medium">
                        <span
                          className="hover-tip hover-tip--wrap hover-tip--right"
                          data-tip="基金自身口径的近 3 年收益（含同类排名）。与「任职回报」不同：后者按该经理的任职窗口算——经理离任后基金可能已换人"
                        >
                          近3年
                        </span>
                      </th>
                      <th className="w-[7rem] py-1 text-right font-medium">
                        <span
                          className="hover-tip hover-tip--wrap hover-tip--right"
                          data-tip="基金自身口径的近 5 年收益（含同类排名）。与「任职回报」不同：后者按该经理的任职窗口算——经理离任后基金可能已换人"
                        >
                          近5年
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {shownTenures.map(t => (
                      <tr key={`${t.fund_code}-${t.start_date}`} className="border-b border-rule/50 last:border-b-0">
                        <td className="py-1 pr-2 whitespace-nowrap overflow-hidden">
                          <AffiliationBadges aff={t.affiliation} code={t.fund_code} name={t.fund_name} />
                        </td>
                        <td className="py-1 pr-2">
                          {/* table-fixed 下不换行：名称过长时截断（inline span 的
                              truncate 不生效，须用块级） */}
                          <div className="truncate" title={t.fund_name ?? undefined}>{t.fund_name}</div>
                        </td>
                        <td className="py-1 pr-2 text-ink-muted truncate">{t.fund_type ?? '-'}</td>
                        <td className="py-1 pr-2 tnum text-right">{fmtNum(t.size_yi, 1)}</td>
                        <td className="py-1 pr-2 text-ink-muted whitespace-nowrap">{t.start_date}~{t.end_date ?? '至今'}</td>
                        <td className="py-1 pr-2 tnum text-right">{t.tenure_days ?? '-'}</td>
                        <td className={`py-1 pr-2 tnum text-right ${(t.tenure_return ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>
                          {fmtPct(t.tenure_return)}
                        </td>
                        <td className={`py-1 pr-2 tnum text-right ${(t.annual_return ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>
                          {fmtPct(t.annual_return)}
                        </td>
                        <td className="py-1 pr-2 text-right">
                          <div className={`tnum whitespace-nowrap ${retColor(t.ret_1y)}`}>{fmtRet(t.ret_1y)}</div>
                          <div className="flex items-center justify-end gap-1 text-[10px] text-ink-soft shrink-0">
                            <RankInline rank={t.rank_1y} />
                            {t.rank_1y?.rank != null && t.rank_1y?.total != null && (
                              <span>{t.rank_1y.rank}/{t.rank_1y.total}</span>
                            )}
                          </div>
                        </td>
                        <td className="py-1 pr-2 text-right">
                          <div className={`tnum whitespace-nowrap ${retColor(t.ret_3y)}`}>{fmtRet(t.ret_3y)}</div>
                          <div className="flex items-center justify-end gap-1 text-[10px] text-ink-soft shrink-0">
                            <RankInline rank={t.rank_3y} />
                            {t.rank_3y?.rank != null && t.rank_3y?.total != null && (
                              <span>{t.rank_3y.rank}/{t.rank_3y.total}</span>
                            )}
                          </div>
                        </td>
                        <td className="py-1 text-right">
                          <div className={`tnum whitespace-nowrap ${retColor(t.ret_5y)}`}>{fmtRet(t.ret_5y)}</div>
                          <div className="flex items-center justify-end gap-1 text-[10px] text-ink-soft shrink-0">
                            <RankInline rank={t.rank_5y} />
                            {t.rank_5y?.rank != null && t.rank_5y?.total != null && (
                              <span>{t.rank_5y.rank}/{t.rank_5y.total}</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                )}
              </div>
            ) : (
              <span className="text-xs text-ink-muted">无历任基金数据</span>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function ManagersPage() {
  return (
    <Suspense fallback={<div className="p-8 text-ink-muted">加载中…</div>}>
      <ManagersPageInner />
    </Suspense>
  );
}
