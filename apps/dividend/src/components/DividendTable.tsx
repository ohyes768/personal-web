/**
 * 股息率表格组件
 */
'use client';

import { Button } from './shared-ui/Button';
import { CheckIcon, ChevronUpIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import { useState, useMemo, useEffect, useRef, useCallback, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import type { DividendStock, TechnicalIndicators } from '@/lib/types';

type SortField = 'avg_yield_3y' | 'realtime_yield';
type SortOrder = 'asc' | 'desc';

const formatValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return value.toFixed(2);
};

/**
 * 格式化实时股息率
 */
const formatRealtimeYield = (dividend2025: number | null | undefined, realtime: number | null | undefined): string => {
  if (!dividend2025 || !realtime) return '-';
  const yield_pct = dividend2025 / realtime * 100;
  return yield_pct.toFixed(2) + '%';
};

/**
 * 计算实时股息率数值（用于排序）
 */
const calcRealtimeYieldValue = (dividend2025: number | null | undefined, realtime: number | null | undefined): number => {
  if (!dividend2025 || !realtime) return 0;
  return dividend2025 / realtime * 100;
};

/**
 * 格式化实时股息率TTM
 */
const formatYieldTtm = (technical: TechnicalIndicators | null): string => {
  if (!technical || technical.yield_ttm === null || technical.yield_ttm === undefined) return '-';
  return technical.yield_ttm.toFixed(2) + '%';
};

const formatSwIndustry = (stock: DividendStock): string[] => {
  return [
    stock.sw_level1 || '-',
    stock.sw_level2 || '-',
    stock.sw_level3 || '-',
  ];
};

/**
 * 格式化 M120 列
 */
const formatM120 = (technical: TechnicalIndicators | null): string => {
  if (!technical || !technical.m120) {
    return '-';
  }
  return formatValue(technical.m120);
};

/**
 * 格式化股东户数（转换为万单位）
 */
const formatShareholderCount = (count: number | null | undefined): string => {
  if (count === null || count === undefined) return '-';
  return (count / 10000).toFixed(1) + '万';
};

/**
 * 格式化 扣非净利润(元) → 亿元
 */
const formatYi = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return (value / 1e8).toFixed(2) + '亿';
};

/**
 * 格式化 昨日/M120 列
 */
const formatPriceDeviation = (technical: TechnicalIndicators | null): {
  line1: string;
  line2: string;
  line1Class?: string;
  line2Class?: string;
} => {
  if (!technical || !technical.m120) {
    return { line1: '-', line2: '实时：-（-）' };
  }

  const close = technical.close !== null && technical.close !== undefined ? formatValue(technical.close) : '-';

  // 计算昨日收盘/M120 的比率及颜色
  let ratioStr = '-';
  let ratioClass = '';
  if (technical.close !== null && technical.close !== undefined && technical.m120) {
    const ratio = technical.close / technical.m120;
    ratioStr = ratio.toFixed(3);
    if (ratio < 0.90) {
      ratioClass = 'text-green-400';
    } else if (ratio > 1.10) {
      ratioClass = 'text-red-500';
    }
  }

  const line1 = `昨日收盘：${close}（<span class="${ratioClass}">${ratioStr}</span>）`;

  // 实时数据（从CSV获取）
  const realtimeClose = technical.realtime !== null && technical.realtime !== undefined
    ? formatValue(technical.realtime)
    : '-';

  let realtimeRatioStr = '-';
  let realtimeRatioClass = '';
  if (technical.realtime !== null && technical.realtime !== undefined && technical.m120) {
    const realtimeRatio = technical.realtime / technical.m120;
    realtimeRatioStr = realtimeRatio.toFixed(3);
    if (realtimeRatio < 0.90) {
      realtimeRatioClass = 'text-green-400';
    } else if (realtimeRatio > 1.10) {
      realtimeRatioClass = 'text-red-500';
    }
  }

  const line2 = `实时：${realtimeClose}（<span class="${realtimeRatioClass}">${realtimeRatioStr}</span>）`;

  return { line1, line2 };
};

export interface DividendTableProps {
  data: DividendStock[];
  technicalData: Map<string, TechnicalIndicators>;
  onOpenModal: (type: 'quarterly' | 'sector' | 'yearly' | 'volatility', stock: DividendStock) => void;
  selectedStockCodes: string[];
  maxSelect: number;
  onToggleCompare: (stock: DividendStock) => void;
  defaultSortField?: SortField;
  defaultSortOrder?: SortOrder;
}

export function DividendTable({
  data,
  technicalData,
  onOpenModal,
  selectedStockCodes,
  maxSelect,
  onToggleCompare,
  defaultSortField = 'avg_yield_3y',
  defaultSortOrder = 'desc',
}: DividendTableProps) {
  const [sortField, setSortField] = useState<SortField>(defaultSortField);
  const [sortOrder, setSortOrder] = useState<SortOrder>(defaultSortOrder);
  // popover：扣非同比 / TTM 共用同一状态，kind 区分内容
  const [popover, setPopover] = useState<{
    code: string;
    rect: DOMRect;
    stock: DividendStock;
    kind: 'koufei' | 'ttm';
  } | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const closePopover = useCallback(() => setPopover(null), []);

  // ESC 关闭 + 点击外部关闭
  useEffect(() => {
    if (!popover) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closePopover();
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node | null;
      if (!t) return;
      if (popoverRef.current && popoverRef.current.contains(t)) return;
      // 触发 cell 用 data-attr 标记，含 kind 前缀避免重码
      const trigger = document.querySelector(`[data-popover-trigger="${popover.kind}:${popover.code}"]`);
      if (trigger && trigger.contains(t)) return;
      closePopover();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [popover, closePopover]);

  // 排序后的数据
  const sortedData = useMemo(() => {
    return [...data].sort((a, b) => {
      let aVal: number, bVal: number;

      if (sortField === 'avg_yield_3y') {
        aVal = a.avg_yield_3y ?? 0;
        bVal = b.avg_yield_3y ?? 0;
      } else if (sortField === 'realtime_yield') {
        const techA = technicalData.get(a.code);
        const techB = technicalData.get(b.code);
        aVal = calcRealtimeYieldValue(a.dividend_2025, techA?.realtime ?? null);
        bVal = calcRealtimeYieldValue(b.dividend_2025, techB?.realtime ?? null);
      } else {
        // 不应到达（SortField 已移除 yield_ttm），兜底用 3 年平均
        aVal = a.avg_yield_3y ?? 0;
        bVal = b.avg_yield_3y ?? 0;
      }

      if (aVal === bVal) return 0;
      const cmp = aVal > bVal ? 1 : -1;
      return sortOrder === 'desc' ? -cmp : cmp;
    });
  }, [data, technicalData, sortField, sortOrder]);

  // 切换排序
  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  // 渲染排序图标
  const SortIcon = ({ field }: { field: SortField }) => {
    if (field !== sortField) {
      return <span className="opacity-30">↕</span>;
    }
    return sortOrder === 'desc'
      ? <ChevronDownIcon className="w-3 h-3 inline" />
      : <ChevronUpIcon className="w-3 h-3 inline" />;
  };
  if (data.length === 0) {
    return (
      <div className="border border-gray-700 rounded-lg overflow-hidden bg-gray-900">
        <div className="py-8 flex items-center justify-center text-gray-400">
          暂无数据
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="border border-gray-700 rounded-lg overflow-hidden bg-gray-900">
      <table className="w-full">
        <thead className="bg-gray-800">
          <tr>
            <th className="w-16 px-2 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              代码
            </th>
            <th className="w-24 px-2 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              名称
            </th>
            <th className="w-12 px-1 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              市场
            </th>
            <th className="w-28 px-2 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              行业
            </th>
            <th
              className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 whitespace-nowrap cursor-pointer hover:text-white select-none"
              onClick={() => handleSort('avg_yield_3y')}
            >
              3年股息率 <SortIcon field="avg_yield_3y" />
            </th>
            <th
              className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 whitespace-nowrap cursor-pointer hover:text-white select-none"
              onClick={() => handleSort('realtime_yield')}
            >
              实时股息率 <SortIcon field="realtime_yield" />
            </th>
            <th className="w-16 px-2 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              M120
            </th>
            <th className="w-20 px-2 py-3 text-left text-xs font-medium text-gray-400 whitespace-nowrap">
              户数
            </th>
            <th className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
              扣非同比
            </th>
            <th className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
              3年CAGR
            </th>
            <th className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider" title="分红比例 = 每股分红 / 每股净利润（最近一期年报）">
              分红比例
            </th>
            <th className="w-56 px-2 py-3 text-left text-xs font-medium text-gray-400 whitespace-nowrap">
              昨日/M120
            </th>
            <th className="w-80 px-2 py-3 text-center text-xs font-medium text-gray-400 uppercase tracking-wider">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedData.map((stock) => {
            const technical = technicalData.get(stock.code) || null;
            const m120Value = formatM120(technical);
            const priceInfo = formatPriceDeviation(technical);
            const isSelected = selectedStockCodes.includes(stock.code);
            const isMaxReached = selectedStockCodes.length >= maxSelect && !isSelected;

            return (
              <tr
                key={stock.code}
                className={`
                  border-b border-gray-800 transition-all duration-200 ease-out cursor-pointer
                  ${isSelected
                    ? 'bg-blue-900/20 border-l-4 border-l-blue-500'
                    : 'hover:bg-gray-800 hover:shadow-md hover:shadow-blue-500/10 border-l-4 border-l-transparent hover:border-l-blue-400'
                  }
                `}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    onOpenModal('quarterly', stock);
                  }
                }}
              >
                <td className="w-16 px-2 py-3 font-mono text-sm text-gray-300">
                  {stock.code}
                </td>
                <td className="w-24 px-2 py-3 text-sm font-medium text-gray-200">
                  {stock.name}
                </td>
                <td className="w-16 px-2 py-3 text-sm text-gray-300">
                  {stock.exchange}
                </td>
                <td className="w-28 px-2 py-3 text-xs text-gray-300 leading-tight">
                  {formatSwIndustry(stock).map((level, index) => (
                    <div key={index} className="truncate">
                      {level}
                    </div>
                  ))}
                </td>
                <td className="w-20 px-2 py-3 text-sm text-right">
                  <span className={
                    stock.avg_yield_3y && stock.avg_yield_3y >= 5
                      ? 'text-green-400 font-semibold'
                      : stock.avg_yield_3y && stock.avg_yield_3y >= 3
                      ? 'text-green-400'
                      : 'text-gray-400'
                  }>
                    {stock.avg_yield_3y ? `${formatValue(stock.avg_yield_3y)}%` : '-'}
                  </span>
                </td>
                <td
                  data-popover-trigger={`ttm:${stock.code}`}
                  className={`w-20 px-2 py-3 text-sm text-right select-none ${
                    technical && technical.yield_ttm !== null && technical.yield_ttm !== undefined
                      ? `cursor-pointer hover:bg-gray-800/60 ${popover?.code === stock.code && popover.kind === 'ttm' ? 'bg-gray-800/60' : ''}`
                      : ''
                  }`}
                  onClick={(e) => {
                    if (!technical || technical.yield_ttm === null || technical.yield_ttm === undefined) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (popover?.code === stock.code && popover.kind === 'ttm') {
                      closePopover();
                    } else {
                      setPopover({ code: stock.code, rect, stock, kind: 'ttm' });
                    }
                  }}
                  title={
                    technical && technical.yield_ttm !== null && technical.yield_ttm !== undefined
                      ? '点击查看 TTM 股息率'
                      : '无 TTM 数据'
                  }
                >
                  {(() => {
                    const realtimeYield = formatRealtimeYield(stock.dividend_2025, technical?.realtime ?? null);
                    if (realtimeYield === '-') return <span className="text-gray-400">-</span>;
                    const yieldVal = parseFloat(realtimeYield);
                    return (
                      <span className={
                        yieldVal >= 5
                          ? 'text-green-400 font-semibold'
                          : yieldVal >= 3
                          ? 'text-green-400'
                          : 'text-gray-400'
                      }>
                        {realtimeYield}
                      </span>
                    );
                  })()}
                </td>
                <td className="w-16 px-2 py-3 text-sm text-gray-300">
                  {m120Value}
                </td>
                <td className="w-20 px-2 py-3 text-sm text-gray-300">
                  {formatShareholderCount(stock.shareholder_count)}
                </td>
                <td
                  data-popover-trigger={`koufei:${stock.code}`}
                  className={`w-20 px-2 py-3 text-sm text-right select-none ${
                    stock.latest_quarter_yoy_pct !== null && stock.latest_quarter_yoy_pct !== undefined
                      ? `cursor-pointer hover:bg-gray-800/60 ${popover?.code === stock.code && popover.kind === 'koufei' ? 'bg-gray-800/60' : ''}`
                      : ''
                  }`}
                  onClick={(e) => {
                    if (stock.latest_quarter_yoy_pct === null || stock.latest_quarter_yoy_pct === undefined) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (popover?.code === stock.code && popover.kind === 'koufei') {
                      closePopover();
                    } else {
                      setPopover({ code: stock.code, rect, stock, kind: 'koufei' });
                    }
                  }}
                  title={
                    stock.latest_quarter_yoy_pct !== null && stock.latest_quarter_yoy_pct !== undefined
                      ? '点击查看 2026Q1 扣非同比'
                      : '无最新季度数据'
                  }
                >
                  {(() => {
                    const v = stock.net_profit_ex_non_recurring_yoy;
                    if (v !== null && v !== undefined) {
                      return (
                        <span className={v > 0 ? 'text-green-400' : 'text-red-400'}>
                          {v > 0 ? '+' : ''}{v.toFixed(2)}%
                        </span>
                      );
                    }
                    return '无法计算';
                  })()}
                </td>
                <td className="w-20 px-2 py-3 text-sm text-right">
                  {stock.net_profit_cagr_3y !== null && stock.net_profit_cagr_3y !== undefined
                    ? (
                      <span className={stock.net_profit_cagr_3y > 0 ? 'text-green-400' : 'text-red-400'}>
                        {stock.net_profit_cagr_3y > 0 ? '+' : ''}{stock.net_profit_cagr_3y.toFixed(2)}%
                      </span>
                    )
                    : '无法计算'}
                </td>
                <td className="w-20 px-2 py-3 text-sm text-right">
                  {stock.payout_ratio !== null && stock.payout_ratio !== undefined
                    ? (
                      <span
                        className={
                          stock.payout_ratio < 30 ? 'text-gray-400' :
                          stock.payout_ratio < 60 ? 'text-yellow-400' :
                          stock.payout_ratio <= 80 ? 'text-green-400' :
                          'text-orange-400'
                        }
                        title={`基于 ${stock.eps_year ?? '?'} 年报 EPS = ${stock.eps?.toFixed(2) ?? '?'} 元`}
                      >
                        {stock.payout_ratio.toFixed(2)}%
                      </span>
                    )
                    : '亏损/-'}
                </td>
                <td className="w-56 px-2 py-3 text-xs text-gray-300 leading-tight">
                  <div className="text-xs leading-tight">
                    <div dangerouslySetInnerHTML={{ __html: priceInfo.line1 }} />
                    <div className="flex items-center gap-1 mt-1">
                      <span dangerouslySetInnerHTML={{ __html: priceInfo.line2 }} />
                    </div>
                  </div>
                </td>
                <td className="w-80 px-2 py-3 text-center">
                  <div className="flex items-center justify-center gap-2">
                    <Button
                      variant={isSelected ? 'primary' : 'ghost'}
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleCompare(stock);
                      }}
                      disabled={isMaxReached}
                      className={`
                        h-8 min-w-[60px] flex items-center gap-1
                        transition-all duration-200
                        ${isMaxReached
                          ? 'opacity-50 cursor-not-allowed'
                          : ''
                        }
                      `}
                      aria-label={isSelected
                        ? `取消选中 ${stock.name} 进行对比`
                        : `选中 ${stock.name} 进行对比`
                      }
                    >
                      {isSelected && <CheckIcon className="w-4 h-4" />}
                      对比
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenModal('yearly', stock);
                      }}
                      className="h-7 px-2.5 text-sm text-white font-medium border border-gray-500 bg-gray-800/80 hover:bg-blue-500 hover:border-blue-400 shadow-sm shadow-black/50 transition-all duration-200"
                    >
                      年度
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenModal('quarterly', stock);
                      }}
                      className="h-7 px-2.5 text-sm text-white font-medium border border-gray-500 bg-gray-800/80 hover:bg-blue-500 hover:border-blue-400 shadow-sm shadow-black/50 transition-all duration-200"
                    >
                      记录
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenModal('sector', stock);
                      }}
                      className="h-7 px-2.5 text-sm text-white font-medium border border-gray-500 bg-gray-800/80 hover:bg-blue-500 hover:border-blue-400 shadow-sm shadow-black/50 transition-all duration-200"
                    >
                      板块
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenModal('volatility', stock);
                      }}
                      className="h-7 px-2.5 text-sm text-white font-medium border border-gray-500 bg-gray-800/80 hover:bg-blue-500 hover:border-blue-400 shadow-sm shadow-black/50 transition-all duration-200"
                    >
                      波动
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {mounted && popover && createPortal(
      <FinancialPopover
        ref={popoverRef}
        stock={popover.stock}
        anchorRect={popover.rect}
        kind={popover.kind}
        technical={technicalData.get(popover.code) ?? null}
      />,
      document.body,
    )}
    </>
  );
}

/**
 * 财务 popover：扣非同比 / TTM 股息率 共用组件，按 kind 渲染不同内容。
 */
type FinancialPopoverProps = {
  stock: DividendStock;
  anchorRect: DOMRect;
  kind: 'koufei' | 'ttm';
  technical: TechnicalIndicators | null;
};

const FinancialPopover = forwardRef<HTMLDivElement, FinancialPopoverProps>(function FinancialPopover(
  { stock, anchorRect, kind, technical },
  ref,
) {
  // 位置：默认 cell 上方；上方空间不够则下方
  const popHeight = 130;
  const placeAbove = anchorRect.top > popHeight + 16;
  const top = placeAbove ? anchorRect.top - 12 : anchorRect.bottom + 12;
  const transformY = placeAbove ? '-100%' : '0%';
  const arrowPos = placeAbove ? '-bottom-2' : '-top-2';
  const arrowRotate = placeAbove ? 'rotate-180' : '';

  // ----- koufei: 2026Q1 扣非同比 -----
  if (kind === 'koufei') {
    const yoy = stock.latest_quarter_yoy_pct;
    const amount = stock.latest_quarter_net_profit_ex_non_recurring;
    if (yoy === null || yoy === undefined) return null;
    const positive = yoy >= 0;
    const accent = positive ? 'bg-emerald-500' : 'bg-rose-500';
    const accentText = positive ? 'text-emerald-400' : 'text-rose-400';

    return (
      <PopoverShell
        ref={ref}
        anchorRect={anchorRect}
        top={top}
        transformY={transformY}
        arrowPos={arrowPos}
        arrowRotate={arrowRotate}
        accent={accent}
        ariaLabel="最新季度扣非同比详情"
      >
        <div className="px-4 pt-3 pb-1.5">
          <div className="flex items-center gap-2">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${accent}`} aria-hidden />
            <span className="text-[11px] font-semibold tracking-wider text-gray-200">
              2026Q1 扣非同比
            </span>
          </div>
          <div className="text-[10px] text-gray-500 mt-0.5 pl-3.5 font-mono">
            vs 2025Q1
          </div>
        </div>

        <div className="px-4 pb-3">
          <div className={`flex items-baseline gap-1.5 font-mono ${accentText}`}>
            <span className="text-xs opacity-70 leading-none">{positive ? '↑' : '↓'}</span>
            <span className="text-[26px] font-bold tabular-nums leading-none">
              {positive ? '+' : ''}{yoy.toFixed(2)}<span className="text-base ml-0.5">%</span>
            </span>
          </div>
          {amount !== null && amount !== undefined && (
            <div className="text-xs text-gray-400 mt-2">
              扣非净利润{' '}
              <span className="font-mono text-gray-200 tabular-nums">
                {formatYi(amount)}
              </span>
            </div>
          )}
        </div>
      </PopoverShell>
    );
  }

  // ----- ttm: TTM 股息率 -----
  const ttm = technical?.yield_ttm ?? null;
  if (ttm === null || ttm === undefined) return null;

  const realtime = technical?.realtime ?? null;
  const realtimeYieldStr = realtime !== null && stock.dividend_2025
    ? `${(stock.dividend_2025 / realtime * 100).toFixed(2)}%`
    : null;

  // TTM 颜色：>=5 绿加粗，>=3 绿，否则灰
  const ttmClass = ttm >= 5
    ? 'text-emerald-400'
    : ttm >= 3
    ? 'text-emerald-300'
    : 'text-gray-300';
  const accent = 'bg-sky-500';

  return (
    <PopoverShell
      ref={ref}
      anchorRect={anchorRect}
      top={top}
      transformY={transformY}
      arrowPos={arrowPos}
      arrowRotate={arrowRotate}
      accent={accent}
      ariaLabel="TTM 股息率详情"
    >
      <div className="px-4 pt-3 pb-1.5">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${accent}`} aria-hidden />
          <span className="text-[11px] font-semibold tracking-wider text-gray-200">
            TTM 股息率
          </span>
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5 pl-3.5 font-mono">
          滚动 12 月 / 实时价
        </div>
      </div>

      <div className="px-4 pb-3">
        <div className={`flex items-baseline gap-1.5 font-mono ${ttmClass}`}>
          <span className="text-[26px] font-bold tabular-nums leading-none">
            {ttm.toFixed(2)}<span className="text-base ml-0.5">%</span>
          </span>
        </div>
        {realtimeYieldStr !== null && (
          <div className="text-xs text-gray-400 mt-2">
            实时股息率{' '}
            <span className="font-mono text-gray-200 tabular-nums">{realtimeYieldStr}</span>
          </div>
        )}
      </div>
    </PopoverShell>
  );
});

/**
 * Popover 外壳：定位 + 边框 + 箭头。两个 kind 共用。
 */
type PopoverShellProps = {
  anchorRect: DOMRect;
  top: number;
  transformY: string;
  arrowPos: string;
  arrowRotate: string;
  accent: string;
  ariaLabel: string;
  children: React.ReactNode;
};

const PopoverShell = forwardRef<HTMLDivElement, PopoverShellProps>(function PopoverShell(
  { anchorRect, top, transformY, arrowPos, arrowRotate, accent, ariaLabel, children },
  ref,
) {
  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={ariaLabel}
      className="fixed z-50 w-60 rounded-md bg-gray-900 border border-blue-500/30 shadow-2xl shadow-black/70"
      style={{
        left: anchorRect.left + anchorRect.width / 2,
        top,
        transform: `translateX(-50%) translateY(${transformY})`,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* 左 border accent */}
      <div className={`absolute left-0 top-0 bottom-0 w-0.5 rounded-l-md ${accent}`} aria-hidden />

      {children}

      {/* 底部/顶部箭头 */}
      <div
        className={`absolute left-1/2 -translate-x-1/2 ${arrowPos} ${arrowRotate}`}
        aria-hidden
      >
        <div
          className="w-0 h-0"
          style={{
            borderLeft: '7px solid transparent',
            borderRight: '7px solid transparent',
            borderTop: '7px solid rgb(17, 24, 39)',
            filter: 'drop-shadow(0 1px 0 rgba(59, 130, 246, 0.3))',
          }}
        />
      </div>
    </div>
  );
});