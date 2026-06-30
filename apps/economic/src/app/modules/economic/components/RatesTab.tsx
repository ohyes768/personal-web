'use client';

/**
 * 利率利差 Tab — 容器组件
 * - 展示 SOFR + 美债3M + TED 利差 + 中国10y + 中国10年-2年
 * - 数据源独立 InitButton + RefreshButton（参考 LiquidityTab 模板）
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
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

interface RatesTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function RatesTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: RatesTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="rates" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initRatesHistory}
          storageKey="last_initialized_macro_rates"
          label="初始化利率利差"
          hasData={!!(data?.ted_spread?.ted_spread?.length || data?.china_bond?.['spread_10y_2y']?.length)}
        />
        <RefreshButton
          onRefresh={economicApi.updateRates}
          storageKey="last_updated_rates_daily"
          cadence="daily"
          label="更新利率利差"
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

      {isLoading && (
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400">加载利率利差数据中...</p>
        </div>
      )}
    </div>
  );
}