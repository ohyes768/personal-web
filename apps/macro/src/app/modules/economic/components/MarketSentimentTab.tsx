'use client';

/**
 * 市场情绪 Tab — 容器组件
 *
 * 数据源：EconomicDataResponse.volume / turnover / margin / fund_flow
 * 写入：InitButton → 串行 /fetch/volume-turnover/history → /fetch/margin/history → /fetch/fund-flow/history；
 *       RefreshButton → 串行 update volume/turnover/margin/fund-flow
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { MarketSentimentChart } from './MarketSentimentChart';
import { HsgtFundFlowChart } from './HsgtFundFlowChart';
import { TabPanelLoading } from './TabPanelLoading';

interface MarketSentimentTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function MarketSentimentTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess,
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
        <InitButton
          onInit={economicApi.initMarketSentimentHistory}
          storageKey="last_initialized_macro_market_sentiment"
          label="初始化历史数据"
          hasData={
            !!(
              fullData?.volume?.length &&
              fullData?.turnover?.length &&
              fullData?.fund_flow?.north_deal_amount?.length
            )
          }
          onSuccess={onRefreshSuccess}
        />
        <RefreshButton
          onRefresh={economicApi.updateMarketSentiment}
          storageKey="last_updated_market_sentiment_daily"
          cadence="daily"
          label="更新数据"
          onSuccess={onRefreshSuccess}
        />
      </div>

      {error && (
        <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">获取数据失败</p>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {data && !isLoading && (
        <>
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <MarketSentimentChart data={data} />
          </div>
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <HsgtFundFlowChart data={data} />
          </div>
        </>
      )}

      {isLoading && <TabPanelLoading message="加载市场情绪数据中…" />}
    </div>
  );
}
