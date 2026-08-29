'use client';

/**
 * 市场情绪 Tab — 容器组件
 *
 * 数据源：EconomicDataResponse.volume / turnover / margin 三个扁平数组
 * 数据流：page 按 Tab 请求 /api/macro/data/market-sentiment → useFilteredEconomicData 本地切片
 *
 * 注：本 tab 数据由后端每日盘后调度（n8n POST /api/macro/update/volume/turnover/margin）追加，
 * 无需前端 InitButton / RefreshButton。CSV 自然累积。
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { TimeRangeSelector } from './TimeRangeSelector';
import { MarketSentimentChart } from './MarketSentimentChart';
import { TabPanelLoading } from './TabPanelLoading';

interface MarketSentimentTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function MarketSentimentTab({
  timeRange,
  onTimeRangeChange,
  fullData,
  isLoading,
  error,
}: MarketSentimentTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'market-sentiment');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="rates" />
        <span className="text-xs text-gray-500">
          数据由后端每日盘后 16:30 调度自动追加（无需手动刷新）
        </span>
      </div>

      {error && (
        <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">获取数据失败</p>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {data && !isLoading && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <MarketSentimentChart data={data} />
        </div>
      )}

      {isLoading && <TabPanelLoading message="加载市场情绪数据中…" />}
    </div>
  );
}