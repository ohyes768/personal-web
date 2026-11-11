/**
 * 经理维度 Tab（/funds/managers，任务 11-10-fund-manager-evaluation）
 *
 * 以经理为主体的列表：从业年限 / 加权年化 / 回撤 / 规模筛选 + 排序 + 分页。
 * 点击行展开历任基金（含已离任，按需拉取 /managers/{id}）。
 * 只读页面，无刷新入口（采集走 scheduler / 手动脚本，不在页面伪造）。
 */
'use client';

import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { useCallback, useEffect, useRef, useState } from 'react';

import { FundsNavigation } from '@/components/FundsNavigation';
import { Pagination } from '@/components/Pagination';
import {
  MANAGER_DEFAULT_FILTERS,
  managerApi,
  type ManagerDetail,
  type ManagerFilters,
  type ManagerListItem,
  type ManagerScreenResponse,
} from '@/lib/managers';

const fmtPct = (v: number | null, digits = 1) =>
  v != null ? `${v.toFixed(digits)}%` : '-';
const fmtNum = (v: number | null, digits = 1) => (v != null ? v.toFixed(digits) : '-');

export default function ManagersPage() {
  const [filters, setFilters] = useState<ManagerFilters>(MANAGER_DEFAULT_FILTERS);
  const [data, setData] = useState<ManagerScreenResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 展开的经理详情（按需拉取）
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ManagerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const setFilter = useCallback(<K extends keyof ManagerFilters>(key: K, value: ManagerFilters[K]) => {
    setFilters(prev => ({ ...prev, [key]: value, page: 1 }));
  }, []);

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

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-10 bg-paper/95 backdrop-blur border-b border-rule">
        <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between gap-3">
          <h1 className="text-base font-semibold text-ink-strong whitespace-nowrap">经理·股票基金</h1>
          <FundsNavigation active="managers" />
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-4">
        {/* 筛选栏 */}
        <div className="flex items-center gap-2 flex-wrap text-sm mb-3">
          <NumInput label="从业≥" value={filters.min_career_years} unit="年"
            onChange={v => setFilter('min_career_years', v)} />
          <NumInput label="年化≥" value={filters.min_weighted_annual} unit="%"
            onChange={v => setFilter('min_weighted_annual', v)} />
          <NumInput label="回撤≤" value={filters.max_drawdown} unit="%"
            onChange={v => setFilter('max_drawdown', v)} />
          <NumInput label="规模≥" value={filters.min_scale_yi} unit="亿"
            onChange={v => setFilter('min_scale_yi', v)} />
          <input
            value={filters.keyword ?? ''}
            onChange={e => setFilter('keyword', e.target.value || null)}
            placeholder="姓名/公司"
            className="border border-rule rounded px-2 py-1 w-28 bg-white"
            aria-label="搜索经理"
          />
          <button
            onClick={() => setFilters(MANAGER_DEFAULT_FILTERS)}
            className="text-ink-muted hover:text-ink-strong underline text-xs"
          >
            重置
          </button>
          <span className="ml-auto text-ink-muted text-xs">
            {loading ? '加载中…' : data ? `共 ${data.total} 人` : ''}
          </span>
        </div>

        {error && (
          <div className="mb-3 text-sm text-red-600" role="alert">{error}</div>
        )}

        {/* 表格 */}
        <div className="bg-white rounded border border-rule overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-muted border-b border-rule text-xs">
                <SortableTh label="经理" active={filters} setFilter={setFilter} sortKey="name" />
                <th className="px-2 py-2">公司</th>
                <SortableTh label="从业" active={filters} setFilter={setFilter} sortKey="career_years" />
                <SortableTh label="加权年化" active={filters} setFilter={setFilter} sortKey="weighted_annual" />
                <SortableTh label="最长任期" active={filters} setFilter={setFilter} sortKey="managed_fund_count" />
                <SortableTh label="回撤" active={filters} setFilter={setFilter} sortKey="max_drawdown" />
                <SortableTh label="夏普" active={filters} setFilter={setFilter} sortKey="sharpe" />
                <SortableTh label="规模" active={filters} setFilter={setFilter} sortKey="current_scale_yi" />
                <th className="px-2 py-2 text-right">在管</th>
              </tr>
            </thead>
            <tbody>
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
              {!loading && data && data.items.length === 0 && (
                <tr><td colSpan={9} className="px-2 py-8 text-center text-ink-muted">
                  没有符合条件的经理
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
        <Pagination
          page={filters.page}
          limit={filters.limit}
          total={data?.total ?? 0}
          onPageChange={p => setFilter('page', p)}
          onLimitChange={n => setFilter('limit', n)}
        />

        <p className="mt-4 text-xs text-ink-muted leading-relaxed">
          口径说明：加权年化 = 排除债基/货币/FOF 后按管理天数加权（避免经理自选代表作）；
          回撤/夏普取代表基金（主动权益优先、任期最长、在管优先）按任职窗口的复权净值计算。
          数据源：天天基金经理档案（每日非实时）。
        </p>
      </main>
    </div>
  );
}

function ManagerRow({ manager: m, expanded, detail, detailLoading, onToggle }: {
  manager: ManagerListItem;
  expanded: boolean;
  detail: ManagerDetail | null;
  detailLoading: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className={`border-b border-rule cursor-pointer transition-colors hover:bg-paper-tint ${expanded ? 'bg-info-tint' : ''}`}
      >
        <td className="px-2 py-1.5 font-medium text-ink-strong whitespace-nowrap">
          {m.name}
          {m.representative_fund && (
            <span className="ml-1 text-[10px] text-ink-soft font-mono">{m.representative_fund}</span>
          )}
        </td>
        <td className="px-2 py-1.5 text-ink-muted whitespace-nowrap">{m.company ?? '-'}</td>
        <td className="px-2 py-1.5 tnum text-right">{fmtNum(m.career_years)}</td>
        <td className={`px-2 py-1.5 tnum text-right font-medium ${(m.weighted_annual ?? 0) >= 10 ? 'text-up' : (m.weighted_annual ?? 0) < 0 ? 'text-down' : ''}`}>
          {fmtPct(m.weighted_annual)}
        </td>
        <td className="px-2 py-1.5 tnum text-right">{fmtNum(m.longest_tenure_years)}</td>
        <td className={`px-2 py-1.5 tnum text-right ${(m.max_drawdown ?? 0) <= -60 ? 'text-down' : ''}`}>
          {fmtPct(m.max_drawdown)}
        </td>
        <td className="px-2 py-1.5 tnum text-right">{fmtNum(m.sharpe, 2)}</td>
        <td className="px-2 py-1.5 tnum text-right">{fmtNum(m.current_scale_yi, 0)}</td>
        <td className="px-2 py-1.5 tnum text-right text-ink-muted">
          {m.current_fund_count ?? '-'}/{m.managed_fund_count ?? '-'}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-paper-tint">
          <td colSpan={9} className="px-4 py-3">
            {detailLoading ? (
              <span className="text-xs text-ink-muted inline-flex items-center gap-1">
                <ArrowPathIcon className="w-3 h-3 animate-spin" /> 加载历任基金…
              </span>
            ) : detail?.tenures?.length ? (
              <div>
                <div className="text-xs text-ink-muted mb-1">
                  历任基金 {detail.tenures.length} 只（含离任）· 代表基金按高亮行计算风险指标
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-ink-muted border-b border-rule">
                      <th className="py-1 pr-2">代码</th>
                      <th className="py-1 pr-2">名称</th>
                      <th className="py-1 pr-2">类型</th>
                      <th className="py-1 pr-2 text-right">规模(亿)</th>
                      <th className="py-1 pr-2">任职期间</th>
                      <th className="py-1 pr-2 text-right">天数</th>
                      <th className="py-1 pr-2 text-right">任职回报</th>
                      <th className="py-1 text-right">年化</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.tenures.map(t => (
                      <tr key={`${t.fund_code}-${t.start_date}`} className="border-b border-rule/50">
                        <td className="py-1 pr-2 font-mono text-info">{t.fund_code}</td>
                        <td className="py-1 pr-2">
                          {t.fund_name}
                          {!t.is_current && <span className="ml-1 text-[10px] text-ink-soft">已离任</span>}
                        </td>
                        <td className="py-1 pr-2 text-ink-muted">{t.fund_type ?? '-'}</td>
                        <td className="py-1 pr-2 tnum text-right">{fmtNum(t.size_yi, 1)}</td>
                        <td className="py-1 pr-2 text-ink-muted">{t.start_date}~{t.end_date ?? '至今'}</td>
                        <td className="py-1 pr-2 tnum text-right">{t.tenure_days ?? '-'}</td>
                        <td className={`py-1 pr-2 tnum text-right ${(t.tenure_return ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>
                          {fmtPct(t.tenure_return)}
                        </td>
                        <td className={`py-1 tnum text-right ${(t.annual_return ?? 0) >= 0 ? 'text-up' : 'text-down'}`}>
                          {fmtPct(t.annual_return)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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

function NumInput({ label, value, unit, onChange }: {
  label: string;
  value: number | null;
  unit: string;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="inline-flex items-center gap-1 text-ink-muted">
      {label}
      <input
        type="number"
        value={value ?? ''}
        onChange={e => {
          const v = e.target.value;
          onChange(v === '' ? null : Number(v));
        }}
        className="border border-rule rounded px-1.5 py-1 w-16 bg-white tnum"
        aria-label={label}
      />
      {unit}
    </label>
  );
}

function SortableTh({ label, active, setFilter, sortKey }: {
  label: string;
  active: ManagerFilters;
  setFilter: <K extends keyof ManagerFilters>(key: K, value: ManagerFilters[K]) => void;
  sortKey: string;
}) {
  const isActive = active.sort === sortKey;
  return (
    <th className="px-2 py-2 text-right">
      <button
        onClick={() => setFilter('sort' as keyof ManagerFilters, sortKey as never)}
        onDoubleClick={() => setFilter('order', isActive && active.order === 'desc' ? 'asc' : 'desc')}
        className={`hover:text-ink-strong ${isActive ? 'text-ink-strong' : ''}`}
        title="单击按此列排序（默认降序），双击切换升/降"
      >
        {label}
        {isActive && <span className="ml-0.5">{active.order === 'asc' ? '↑' : '↓'}</span>}
      </button>
    </th>
  );
}
