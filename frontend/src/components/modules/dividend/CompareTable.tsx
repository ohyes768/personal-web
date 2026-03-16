/**
 * 股票对比表格组件
 */
'use client';

import { StarIcon, XMarkIcon, TagIcon, ChartBarIcon, CalendarIcon, ArrowTrendingUpIcon, ArrowTrendingDownIcon } from '@heroicons/react/24/outline';
import { CompareTableProps, DividendStockWithTechnical } from '@/lib/modules/dividend/types';
import { useHighlights } from '@/lib/modules/dividend/hooks';

const formatValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return value.toFixed(2);
};

const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(2)}%`;
};

const formatPrice = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return value.toFixed(2);
};

const formatDividend = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return `每股${value.toFixed(2)}元`;
};

export function CompareTable({ stocks, onRemove }: CompareTableProps) {
  // 计算高亮信息
  const highlights = useHighlights(stocks);

  if (stocks.length === 0) {
    return (
      <div className="text-center py-16">
        <XMarkIcon className="w-16 h-16 mx-auto text-gray-600 mb-4" />
        <h3 className="text-lg font-semibold text-gray-400 mb-2">
          暂无对比数据
        </h3>
        <p className="text-sm text-gray-500">
          请从列表中选择 2-5 只股票进行对比
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        {/* 表头 */}
        <thead className="bg-gray-800 sticky top-0 z-10">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider min-w-[100px] w-[100px]">
              维度
            </th>
            {stocks.map((stock) => (
              <th key={stock.code} className="px-4 py-3 text-center min-w-[120px]">
                <div className="flex items-center justify-center gap-2">
                  <div className="font-medium text-gray-200">{stock.name}</div>
                  <button
                    onClick={() => onRemove(stock.code)}
                    className="flex items-center gap-1 px-2 py-0.5 text-xs text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded transition-colors"
                    aria-label={`移除 ${stock.name}`}
                  >
                    <XMarkIcon className="w-4 h-4" />
                    <span>移除</span>
                  </button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* 元数据 */}
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <TagIcon className="w-4 h-4 text-blue-400" />
                <span>代码</span>
              </div>
            </td>
            {stocks.map((stock) => (
              <td key={stock.code} className="px-4 py-2 text-center text-gray-300 font-mono border-b border-gray-700">
                {stock.code}
              </td>
            ))}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <TagIcon className="w-4 h-4 text-blue-400" />
                <span>名称</span>
              </div>
            </td>
            {stocks.map((stock) => (
              <td key={stock.code} className="px-4 py-2 text-center text-gray-300 border-b border-gray-700">
                {stock.name}
              </td>
            ))}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <TagIcon className="w-4 h-4 text-blue-400" />
                <span>申万行业</span>
              </div>
            </td>
            {stocks.map((stock) => (
              <td key={stock.code} className="px-4 py-2 text-center text-gray-300 border-b border-gray-700">
                {stock.sw_level1 || '-'}
              </td>
            ))}
          </tr>

          {/* 基础指标 */}
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ChartBarIcon className="w-4 h-4 text-green-400" />
                <span>3年股息率</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const isHighlighted = highlights.yieldIndex === idx;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {isHighlighted ? (
                    <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                      <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                      <span className="font-mono">{formatPercent(stock.avg_yield_3y)}</span>
                    </div>
                  ) : (
                    <span className="font-mono">{formatPercent(stock.avg_yield_3y)}</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ChartBarIcon className="w-4 h-4 text-green-400" />
                <span>PE</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const isHighlighted = highlights.peIndex === idx;
              const pe = stock.technical?.pe;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {isHighlighted && pe !== null && pe !== undefined ? (
                    <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                      <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                      <span className="font-mono">{formatValue(pe)}</span>
                    </div>
                  ) : (
                    <span className="font-mono">{formatValue(pe)}</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ChartBarIcon className="w-4 h-4 text-green-400" />
                <span>PB</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const isHighlighted = highlights.pbIndex === idx;
              const pb = stock.technical?.pb;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {isHighlighted && pb !== null && pb !== undefined ? (
                    <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                      <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                      <span className="font-mono">{formatValue(pb)}</span>
                    </div>
                  ) : (
                    <span className="font-mono">{formatValue(pb)}</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ChartBarIcon className="w-4 h-4 text-green-400" />
                <span>昨日收盘/M120</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const technical = stock.technical;
              const ratio = technical?.close && technical?.m120 ? technical.close / technical.m120 : null;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {ratio !== null ? (
                    <>
                      {highlights.ratioIndex === idx ? (
                        <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                          <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                          <span className="font-mono">{ratio.toFixed(3)}</span>
                        </div>
                      ) : (
                        <span className="font-mono">{ratio.toFixed(3)}</span>
                      )}
                    </>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>

          {/* 价格波动 */}
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ArrowTrendingUpIcon className="w-4 h-4 text-orange-400" />
                <span>最高涨幅</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const highChange = stock.high_change_pct_2025;
              const isHighlighted = highlights.highChangeIndex === idx;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {highChange !== null && highChange !== undefined ? (
                    <>
                      {isHighlighted ? (
                        <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                          <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                          <span className="font-mono">{formatPercent(highChange)}</span>
                        </div>
                      ) : (
                        <span className="font-mono text-red-400">{formatPercent(highChange)}</span>
                      )}
                    </>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <ArrowTrendingDownIcon className="w-4 h-4 text-red-400" />
                <span>最高跌幅</span>
              </div>
            </td>
            {stocks.map((stock, idx) => {
              const lowChange = stock.low_change_pct_2025;
              const isHighlighted = highlights.lowChangeIndex === idx;
              return (
                <td key={stock.code} className="px-4 py-2 text-center border-b border-gray-700">
                  {lowChange !== null && lowChange !== undefined ? (
                    <>
                      {isHighlighted ? (
                        <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                          <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                          <span className="font-mono">{formatPercent(lowChange)}</span>
                        </div>
                      ) : (
                        <span className="font-mono text-green-400">{formatPercent(lowChange)}</span>
                      )}
                    </>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>

          {/* 历史股息率 */}
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <CalendarIcon className="w-4 h-4 text-purple-400" />
                <span>2025年股息率</span>
              </div>
            </td>
            {stocks.map((stock) => {
              const yield2025 = stock.yield_2025;
              return (
                <td key={stock.code} className="px-4 py-2 text-center text-gray-300 border-b border-gray-700">
                  {yield2025 !== null && yield2025 !== undefined ? (
                    <span className="font-mono">{formatPercent(yield2025)}</span>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <CalendarIcon className="w-4 h-4 text-purple-400" />
                <span>2024年股息率</span>
              </div>
            </td>
            {stocks.map((stock) => {
              const yield2024 = stock.yield_2024;
              return (
                <td key={stock.code} className="px-4 py-2 text-center text-gray-300 border-b border-gray-700">
                  {yield2024 !== null && yield2024 !== undefined ? (
                    <span className="font-mono">{formatPercent(yield2024)}</span>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>
          <tr className="hover:bg-gray-800/50">
            <td className="px-4 py-2 text-gray-300">
              <div className="flex items-center gap-2">
                <CalendarIcon className="w-4 h-4 text-purple-400" />
                <span>2023年股息率</span>
              </div>
            </td>
            {stocks.map((stock) => {
              const yield2023 = stock.yield_2023;
              return (
                <td key={stock.code} className="px-4 py-2 text-center text-gray-300">
                  {yield2023 !== null && yield2023 !== undefined ? (
                    <span className="font-mono">{formatPercent(yield2023)}</span>
                  ) : (
                    <span>-</span>
                  )}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}