'use client';

/**
 * 中美利差/汇率 Tab — 容器组件
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 做本地时间范围 + tabType 过滤（无网络请求）
 * - 复用 TimeRangeSelector / InitButton / RefreshButton
 * - chartKey 防止数据区间无变化时重复挂载
 */
import { useMemo, useCallback } from 'react';
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { LoadingOverlay } from './LoadingOverlay';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { EconomicChart } from './EconomicChart';

interface TreasuryExchangeTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function TreasuryExchangeTab({
  timeRange,
  onTimeRangeChange,
  refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: TreasuryExchangeTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  const handleRefreshSuccess = useCallback(() => onRefreshSuccess(), [onRefreshSuccess]);

  // 生成图表组件的 key，确保数据变化时重新挂载组件
  const chartKey = useMemo(() => buildChartKey(data), [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 mb-8 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="treasury-exchange" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initHistory}
          storageKey="last_initialized_macro_data"
          label="初始化历史数据"
          hasData={!!data && data.dates && data.dates.length > 0}
        />
        <RefreshButton
          onRefresh={economicApi.updateUsTreasuriesAndRates}
          storageKey="last_updated_us_treasuries_and_rates_daily"
          cadence="daily"
          label="更新中美利差/汇率"
          onSuccess={handleRefreshSuccess}
        />
      </div>

      {error && (
        <div className="mb-8 p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">获取数据失败</p>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {data && !isLoading && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <EconomicChart key={`treasury-${chartKey}`} data={data} showAllData={false} />
        </div>
      )}

      {!isLoading && !data && !error && (
        <div className="text-center py-20">
          <p className="text-gray-400 text-lg">暂无数据</p>
        </div>
      )}

      {isLoading && <LoadingOverlay message="加载经济数据中..." />}
    </div>
  );
}

function buildChartKey(data: EconomicDataResponse | null): string {
  if (!data || data.dates.length === 0) return 'empty';
  const firstDate = data.dates[0] || '';
  const lastDate = data.dates[data.dates.length - 1] || '';
  return firstDate + '-' + lastDate;
}
