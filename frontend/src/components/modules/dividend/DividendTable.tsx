/**
 * 股息率表格组件
 */
'use client';

import { Button } from '@/components/ui/Button';
import type { DividendStock } from '@/lib/modules/dividend/types';

const formatValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return value.toFixed(2);
};

const formatSwIndustry = (stock: DividendStock): string => {
  const parts = [
    stock.sw_level1,
    stock.sw_level2,
    stock.sw_level3,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' / ') : '-';
};

export interface DividendTableProps {
  data: DividendStock[];
  onOpenModal: (type: 'quarterly' | 'sector' | 'yearly' | 'volatility', stock: DividendStock) => void;
}

export function DividendTable({ data, onOpenModal }: DividendTableProps) {
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
      <table className="w-full table-fixed">
        <thead className="bg-gray-800">
          <tr>
            <th className="w-24 px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              股票代码
            </th>
            <th className="w-32 px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              股票名称
            </th>
            <th className="w-24 px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              交易所
            </th>
            <th className="w-64 px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              申万行业
            </th>
            <th className="w-32 px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
              3年平均股息率
            </th>
            <th className="flex-1 px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider min-w-[256px]">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((stock) => (
            <tr
              key={stock.code}
              className="border-b border-gray-800 hover:bg-gray-800 transition-colors cursor-pointer"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onOpenModal('quarterly', stock);
                }
              }}
            >
              <td className="w-24 px-4 py-3 font-mono text-sm text-gray-300">
                {stock.code}
              </td>
              <td className="w-32 px-4 py-3 text-sm font-medium text-gray-200">
                {stock.name}
              </td>
              <td className="w-24 px-4 py-3 text-sm text-gray-300">
                {stock.exchange}
              </td>
              <td className="w-64 px-4 py-3 text-sm text-gray-300 truncate">
                {formatSwIndustry(stock)}
              </td>
              <td className="w-32 px-4 py-3 text-sm text-right">
                <span className={stock.avg_yield_3y && stock.avg_yield_3y >= 3 ? 'text-green-400 font-semibold' : 'text-gray-400'}>
                  {stock.avg_yield_3y ? `${formatValue(stock.avg_yield_3y)}%` : '-'}
                </span>
              </td>
              <td className="flex-1 px-4 py-3 text-sm min-w-[256px]">
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="ghost"
                    onClick={() => onOpenModal('yearly', stock)}
                    className="min-h-[44px] min-w-[44px] px-3 py-2"
                  >
                    年度详情
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => onOpenModal('quarterly', stock)}
                    className="min-h-[44px] min-w-[44px] px-3 py-2"
                  >
                    季度详情
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => onOpenModal('sector', stock)}
                    className="min-h-[44px] min-w-[44px] px-3 py-2"
                  >
                    板块
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => onOpenModal('volatility', stock)}
                    className="min-h-[44px] min-w-[44px] px-3 py-2"
                  >
                    波动
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}