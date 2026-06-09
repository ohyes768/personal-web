/**
 * 指标卡片组件（顶部指标卡片）
 */
import type { CumulativeData } from '@/lib/modules/fund-flow/types';

interface IndicatorCardsProps {
  data: CumulativeData | null;
}

// 格式化金额（亿元）
function formatAmount(value?: number): string {
  if (value === undefined || value === null) return '-';
  return value.toFixed(2);
}

// 根据正负值判断颜色
function getValueColor(value?: number): string {
  if (value === undefined || value === null) return 'text-gray-400';
  return value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-gray-400';
}

export function IndicatorCards({ data }: IndicatorCardsProps) {
  if (!data) {
    return null;
  }

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {/* 北向资金卡片 */}
      <div className="bg-[#1e222d] border border-[#2a2e39] rounded-lg p-6">
        <h3 className="text-lg font-semibold text-[#d1d4dc] mb-4">北向资金</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">7日累计</span>
            <span className={`text-xl font-bold ${getValueColor(data.north_cumulative.cum_7d)}`}>
              {formatAmount(data.north_cumulative.cum_7d)} 亿
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">30日累计</span>
            <span className={`text-xl font-bold ${getValueColor(data.north_cumulative.cum_30d)}`}>
              {formatAmount(data.north_cumulative.cum_30d)} 亿
            </span>
          </div>
        </div>
      </div>

      {/* 南向资金卡片 */}
      <div className="bg-[#1e222d] border border-[#2a2e39] rounded-lg p-6">
        <h3 className="text-lg font-semibold text-[#d1d4dc] mb-4">南向资金</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">7日累计</span>
            <span className={`text-xl font-bold ${getValueColor(data.south_cumulative.cum_7d)}`}>
              {formatAmount(data.south_cumulative.cum_7d)} 亿
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">30日累计</span>
            <span className={`text-xl font-bold ${getValueColor(data.south_cumulative.cum_30d)}`}>
              {formatAmount(data.south_cumulative.cum_30d)} 亿
            </span>
          </div>
        </div>
      </div>

      {/* 净流入卡片 */}
      <div className="bg-[#1e222d] border border-[#2a2e39] rounded-lg p-6">
        <h3 className="text-lg font-semibold text-[#d1d4dc] mb-4">净流入</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">7日累计</span>
            <span className={`text-xl font-bold ${getValueColor(
              (data.north_cumulative.cum_7d ?? 0) - (data.south_cumulative.cum_7d ?? 0)
            )}`}>
              {formatAmount((data.north_cumulative.cum_7d ?? 0) - (data.south_cumulative.cum_7d ?? 0))} 亿
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[#787b86] text-sm">30日累计</span>
            <span className={`text-xl font-bold ${getValueColor(
              (data.north_cumulative.cum_30d ?? 0) - (data.south_cumulative.cum_30d ?? 0)
            )}`}>
              {formatAmount((data.north_cumulative.cum_30d ?? 0) - (data.south_cumulative.cum_30d ?? 0))} 亿
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}