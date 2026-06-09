/**
 * 股息率表格组件
 */
'use client';

import { Button } from './shared-ui/Button';
import { CheckIcon, ChevronUpIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import { useState, useMemo } from 'react';
import type { DividendStock, TechnicalIndicators } from '@/lib/types';

type SortField = 'avg_yield_3y' | 'realtime_yield' | 'yield_ttm';
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
        // yield_ttm
        const techA = technicalData.get(a.code);
        const techB = technicalData.get(b.code);
        aVal = techA?.yield_ttm ?? 0;
        bVal = techB?.yield_ttm ?? 0;
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
            <th
              className="w-20 px-2 py-3 text-right text-xs font-medium text-gray-400 whitespace-nowrap cursor-pointer hover:text-white select-none"
              onClick={() => handleSort('yield_ttm')}
              title="实时股息率 TTM（过去 12 个月滚动分红 / 实时股价）"
            >
              TTM <SortIcon field="yield_ttm" />
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
                <td className="w-20 px-2 py-3 text-sm text-right">
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
                <td className="w-20 px-2 py-3 text-sm text-right">
                  {(() => {
                    const yieldTtm = formatYieldTtm(technical);
                    if (yieldTtm === '-') return <span className="text-gray-400">-</span>;
                    const yieldVal = technical?.yield_ttm ?? 0;
                    return (
                      <span className={
                        yieldVal >= 5
                          ? 'text-green-400 font-semibold'
                          : yieldVal >= 3
                          ? 'text-green-400'
                          : 'text-gray-400'
                      }>
                        {yieldTtm}
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
                <td className="w-20 px-2 py-3 text-sm text-right">
                  {stock.net_profit_ex_non_recurring_yoy !== null && stock.net_profit_ex_non_recurring_yoy !== undefined
                    ? (
                      <span className={stock.net_profit_ex_non_recurring_yoy > 0 ? 'text-green-400' : 'text-red-400'}>
                        {stock.net_profit_ex_non_recurring_yoy > 0 ? '+' : ''}{stock.net_profit_ex_non_recurring_yoy.toFixed(2)}%
                      </span>
                    )
                    : '无法计算'}
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
                          stock.payout_ratio < 30 ? 'text-yellow-400' :
                          stock.payout_ratio > 80 ? 'text-red-400' :
                          'text-green-400'
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
  );
}