'use client';

/**
 * 利率利差 Tab — 容器组件
 * - 展示 SOFR + 美债3M + TED 利差 + 中国10y + 中国10年-2年
 * - 数据源独立 InitButton + RefreshButton（参考 LiquidityTab 模板）
 * - page.tsx 按 Tab 用 useTabEconomicData 拉数，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType
 * - 复用 TimeRangeSelector（rates tabType 走 TREASURY_TIME_RANGES 默认）
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { RatesChart } from './RatesChart';
import { TabPanelLoading } from './TabPanelLoading';

interface RatesTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function RatesTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
}: RatesTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="rates" />
        <InitButton
          onInit={economicApi.initRatesHistory}
          storageKey="last_initialized_macro_rates"
          label="初始化历史数据"
          hasData={!!(data?.ted_spread?.ted_spread?.length || data?.china_bond?.['spread_10y_2y']?.length)}
          onSuccess={onRefreshSuccess}
        />
        <RefreshButton
          onRefresh={economicApi.updateRates}
          storageKey="last_updated_rates_daily"
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
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <RatesChart data={data} />
        </div>
      )}

      {isLoading && <TabPanelLoading message="加载利率利差数据中…" />}
    </div>
  );
}