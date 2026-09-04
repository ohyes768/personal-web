/**
 * 基金主表格：PRD 主表列 + 回撤进度条 + 行末对比按钮 + 排序
 */
'use client';

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
  /** 隐藏「利率债」列（股票 tab 用；债基 tab 默认 true 兼容） */
  showBondColumns?: boolean;
  /** 显示 phase2-B 风险指标 6 列（股票 tab 用） */
  showRiskColumns?: boolean;
}

const NAME_MAX = 10;

/** 风险指标表头悬停说明（均为近 3 年日频口径，公共口径见表格下方脚注） */
const RISK_TIPS: Record<string, string> = {
  sharpe: '夏普比率：每承担 1 份波动，换来的超额收益（相对无风险利率）。>1 优秀；<0 意味着近 3 年还没跑赢无风险收益',
  ir: '信息比率：每 1 份偏离基准的波动，换来的稳定超额，衡量跑赢基准的性价比。>0.5 良好，>1 优秀',
  alpha: '选股α：剔除市场涨跌与择时贡献后，经理纯靠选股获得的年化超额收益。越高选股能力越强；持续为负 = 选股在拖后腿',
  gamma: '择时γ：市场大涨大跌前调仓的能力。>0 涨时跟得上、跌时躲得开；≈0 基本不择时；<0 疑似追涨杀跌',
  alpha_ir: 'α-IR：选股α的稳定度（α÷其波动）。>1 选股能力稳定可信；<0.5 说明 α 忽有忽无，参考价值低',
  excess_3y: '近 3 年累计跑赢基准的幅度（复利口径）',
};

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

/** 小数 → 带符号百分比（选股α / 超额收益，库内为年化小数） */
const fmtPctFromDecimal = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
};

const truncateName = (name: string, max = NAME_MAX): string =>
  name.length > max ? `${name.slice(0, max)}…` : name;

/** 债基页去掉公共前缀，完整类型走 title */
const displayFundType = (type: string): string =>
  type.replace(/^债券型-/, '') || '-';

/** 近 3 年回撤：数字 + 单元格内细条，避免横向占宽 */
function DrawdownBar({ dd }: { dd: number | null }) {
  if (dd === null) return <span className="text-ink-soft">-</span>;
  const pct = Math.min(Math.abs(dd) / 10, 1) * 100;
  return (
    <div className="flex flex-col items-end gap-0.5 min-w-0">
      <span className="tnum text-xs text-down">{dd.toFixed(2)}%</span>
      <div className="w-full max-w-[3.5rem] h-1 bg-rule rounded-full overflow-hidden" aria-hidden="true">
        <div className="h-full bg-down rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function HoverName({ name }: { name: string }) {
  const truncated = name.length > NAME_MAX;
  return (
    <span
      className={truncated ? 'hover-tip' : undefined}
      data-tip={truncated ? name : undefined}
      aria-label={name}
    >
      {truncateName(name)}
    </span>
  );
}

export function FundTable({
  items, loading, error, sort, order, onSort, isSelected, isCompareFull, onToggleCompare,
  showBondColumns = true, showRiskColumns = false,
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

  const th = 'px-1.5 py-2';
  const td = 'px-1.5 py-1.5';

  return (
    <div className="w-full min-w-0">
      <table className="w-full table-fixed text-xs">
        <thead className="border-b border-rule-strong">
          <tr>
            <SortableHeader label="代码" field="code" currentSort={sort} currentOrder={order} onSort={onSort} align="left" />
            <th className={`${th} w-[7rem] text-left text-xs font-medium text-ink-muted`}>名称</th>
            <th className={`${th} text-left text-xs font-medium text-ink-muted`}>类型</th>
            <SortableHeader label="规模" field="size_yi" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="年限" field="age_years" currentSort={sort} currentOrder={order} onSort={onSort} />
            <th className={`${th} text-right text-xs font-medium text-ink-muted`}>回撤</th>
            <SortableHeader label="经理" field="mgr_experience_years" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近1年" field="ret_1y" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近3年" field="ret_3y" currentSort={sort} currentOrder={order} onSort={onSort} />
            <SortableHeader label="近5年" field="ret_5y" currentSort={sort} currentOrder={order} onSort={onSort} />
            {showRiskColumns && (
              <>
                <SortableHeader label="夏普" field="sharpe" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.sharpe} />
                <SortableHeader label="IR" field="ir" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.ir} />
                <SortableHeader label="选股α" field="alpha" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.alpha} />
                <SortableHeader label="择时γ" field="gamma" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.gamma} />
                <SortableHeader label="α-IR" field="alpha_ir" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.alpha_ir} />
                <SortableHeader label="超额3y" field="excess_3y" currentSort={sort} currentOrder={order} onSort={onSort} tip={RISK_TIPS.excess_3y} />
              </>
            )}
            {showBondColumns && <th className={`${th} text-right text-xs font-medium text-ink-muted`}>利率债</th>}
            <SortableHeader label="年费" field="fee_annual" currentSort={sort} currentOrder={order} onSort={onSort} />
            <th className={`${th} text-center text-xs font-medium text-ink-muted`}>对比</th>
          </tr>
        </thead>
        <tbody>
          {items.map(fund => {
            const selected = isSelected(fund.code);
            const disabled = !selected && isCompareFull;
            const typeFull = fund.fund_type || '-';
            const typeShow = displayFundType(typeFull);
            const mgrTip = `${fund.mgr_name || '-'} / ${fund.mgr_company || '-'}`;
            return (
              <tr
                key={fund.code}
                className={`border-b border-rule transition-colors hover:bg-paper-tint ${selected ? 'bg-info-tint' : ''}`}
              >
                <td className={`${td} font-mono text-info whitespace-nowrap`}>{fund.code}</td>
                <td className={`${td} w-[7rem] text-ink-strong`}>
                  <HoverName name={fund.name} />
                </td>
                <td className={`${td} text-ink-muted leading-tight`} title={typeFull}>
                  {typeShow}
                </td>
                <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.size_yi)}</td>
                <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.age_years, 1)}</td>
                <td className={td}><DrawdownBar dd={fund.dd_3y} /></td>
                <td className={`${td} text-right`}>
                  <div className="tnum whitespace-nowrap">{fund.mgr_experience_years != null ? `${fund.mgr_experience_years.toFixed(1)}年` : '-'}</div>
                  <div className="text-[10px] text-ink-soft truncate" title={mgrTip}>
                    {fund.mgr_name || '-'}
                  </div>
                </td>
                <td className={`${td} text-right tnum whitespace-nowrap ${retColor(fund.ret_1y)}`}>{fmtRet(fund.ret_1y)}</td>
                <td className={`${td} text-right tnum whitespace-nowrap ${retColor(fund.ret_3y)}`}>{fmtRet(fund.ret_3y)}</td>
                <td className={`${td} text-right tnum whitespace-nowrap ${retColor(fund.ret_5y)}`}>{fmtRet(fund.ret_5y)}</td>
                {showRiskColumns && (
                  <>
                    <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.sharpe)}</td>
                    <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.ir)}</td>
                    <td className={`${td} text-right tnum whitespace-nowrap ${retColor(fund.alpha)}`}>{fmtPctFromDecimal(fund.alpha)}</td>
                    <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.gamma)}</td>
                    <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.alpha_ir)}</td>
                    <td className={`${td} text-right tnum whitespace-nowrap ${retColor(fund.excess_3y)}`}>{fmtPctFromDecimal(fund.excess_3y)}</td>
                  </>
                )}
                {showBondColumns && <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.rate_bond_pct, 1, '%')}</td>}
                <td className={`${td} text-right tnum whitespace-nowrap`}>{fmt(fund.fee_annual, 2, '%')}</td>
                <td className={`${td} text-center`}>
                  <button
                    onClick={() => onToggleCompare(fund)}
                    disabled={disabled}
                    className={`px-1.5 py-0.5 rounded transition-colors ${
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
      {showRiskColumns && (
        <p className="mt-2 text-[10px] leading-relaxed text-ink-soft">
          风险指标为近 3 年日频口径：基准取各基金业绩基准，无风险利率取 1 年定存；历史不足 250 个交易日的基金显示「-」。
        </p>
      )}
    </div>
  );
}
