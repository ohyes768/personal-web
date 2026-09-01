/**
 * 基金主表格：PRD 主表列 + 回撤进度条 + 行末对比按钮 + 排序
 */
'use client';

import { ScaleIcon } from '@heroicons/react/24/outline';

import type { SortOrder } from './SortableHeader';
import { SortableHeader } from './SortableHeader';
import type { FundListItem } from '@/lib/types';

interface FundTableProps {
  items: FundListItem[];
  loading: boolean;
  error: string | null;
  sort: string;
  order: SortOrder;
  onSort: (field: string) => void;
  isSelected: (code: string) => boolean;
  isCompareFull: boolean;
  onToggleCompare: (fund: FundListItem) => void;
}

const fmt = (v: number | null | undefined, digits = 2, suffix = ''): string => {
  if (v === null || v === undefined) return '-';
  return `${v.toFixed(digits)}${suffix}`;
};

const fmtRet = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

const retColor = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return 'text-ink-soft';
  return v >= 0 ? 'text-up' : 'text-down';
};

/** 近 3 年回撤进度条：满刻度 10%，缺失显示 "-" */
function DrawdownBar({ dd }: { dd: number | null }) {
  if (dd === null) return <span className="text-ink-soft">-</span>;
  const pct = Math.min(Math.abs(dd) / 10, 1) * 100;
  return (
    <div className="flex items-center gap-2 justify-end">
      <span className="tnum text-xs w-12 text-right text-down">{dd.toFixed(2)}%</span>
      <div className="w-16 h-1.5 bg-rule rounded-full overflow-hidden" aria-hidden="true">
        <div className="h-full bg-down rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function FundTable({
  items, loading, error, sort, order, onSort, isSelected, isCompareFull, onToggleCompare,
}: FundTableProps) {
  if (loading) {
    return (
      <div className="p-8 space-y-2 animate-pulse" aria-label="加载中">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-9 bg-paper-tint rounded" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center">
        <p className="text-down mb-3">加载失败：{error}</p>
        <p className="text-sm text-ink-muted">请确认后端已启动（端口 8095）</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="p-12 text-center text-ink-muted">暂无数据，请调整筛选条件</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-rule-strong">
          <tr>
            <SortableHeader label="代码" field="code" currentSort={sort} currentOrder={order} onSort={onSort} align="left" />
            <th className="px-3 py-2 text-left text-xs font-medium text-ink-muted">名称</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-ink-muted">类型</th>
            <SortableHeader label="规模(亿)" field="size_yi" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="成立年限" field="age_years" currentSort={sort} currentOrder={order} onSort={onSort} />
            <th className="px-3 py-2 text-right text-xs font-medium text-ink-muted">
              <span className="inline-flex items-center gap-1 whitespace-nowrap">
                <ScaleIcon className="w-3 h-3 opacity-60" />
                近3年回撤
              </span>
            </th>
            <SortableHeader label="经理" field="mgr_experience_years" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近1年" field="ret_1y" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近3年" field="ret_3y" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近5年" field="ret_5y" currentSort={sort} currentOrder={order} onSort={onSort} />
            <th className="px-3 py-2 text-right text-xs font-medium text-ink-muted">利率债</th>
            <SortableHeader label="年费" field="fee_annual" currentSort={sort} currentOrder={order} onSort={onSort} />
            <th className="px-3 py-2 text-center text-xs font-medium text-ink-muted">对比</th>
          </tr>
        </thead>
        <tbody>
          {items.map(fund => {
            const selected = isSelected(fund.code);
            const disabled = !selected && isCompareFull;
            return (
              <tr
                key={fund.code}
                className={`border-b border-rule transition-colors hover:bg-paper-tint ${selected ? 'bg-info-tint' : ''}`}
              >
                <td className="px-3 py-2 font-mono text-xs text-info">{fund.code}</td>
                <td className="px-3 py-2 text-ink-strong whitespace-nowrap" title={fund.name}>
                  {fund.name}
                </td>
                <td className="px-3 py-2 text-xs text-ink-muted whitespace-nowrap">{fund.fund_type || '-'}</td>
                <td className="px-3 py-2 text-right tnum">{fmt(fund.size_yi)}</td>
                <td className="px-3 py-2 text-right tnum">{fmt(fund.age_years, 1)}</td>
                <td className="px-3 py-2"><DrawdownBar dd={fund.dd_3y} /></td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <div className="tnum text-xs">{fund.mgr_experience_years != null ? `${fund.mgr_experience_years.toFixed(1)}年` : '-'}</div>
                  <div className="text-[10px] text-ink-soft truncate max-w-[90px]" title={`${fund.mgr_name || '-'} / ${fund.mgr_company || '-'}`}>
                    {fund.mgr_name || '-'}
                  </div>
                </td>
                <td className={`px-3 py-2 text-right tnum ${retColor(fund.ret_1y)}`}>{fmtRet(fund.ret_1y)}</td>
                <td className={`px-3 py-2 text-right tnum ${retColor(fund.ret_3y)}`}>{fmtRet(fund.ret_3y)}</td>
                <td className={`px-3 py-2 text-right tnum ${retColor(fund.ret_5y)}`}>{fmtRet(fund.ret_5y)}</td>
                <td className="px-3 py-2 text-right tnum">{fmt(fund.rate_bond_pct, 1)}</td>
                <td className="px-3 py-2 text-right tnum">{fmt(fund.fee_annual)}</td>
                <td className="px-3 py-2 text-center">
                  <button
                    onClick={() => onToggleCompare(fund)}
                    disabled={disabled}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      selected
                        ? 'bg-info text-white'
                        : disabled
                          ? 'bg-paper-deep text-ink-soft cursor-not-allowed'
                          : 'bg-paper-deep text-ink-muted hover:bg-info-tint hover:text-info'
                    }`}
                    aria-label={`对比 ${fund.name}`}
                    aria-pressed={selected}
                  >
                    {selected ? '已选' : '对比'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
