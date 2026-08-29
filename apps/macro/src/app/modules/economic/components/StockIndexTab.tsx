'use client';

/**
 * 股指 Tab — 容器组件
 * - page.tsx 按 Tab 用 useTabEconomicData 拉数，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType（filterDataByTab 对 stock-indices 不裁剪）
 * - 复用 TimeRangeSelector
 * - 复用 RefreshButton（indices 是日级 K 线，cadence=daily）
 * - 复用 InitButton（首次部署用 fetch/indices/history）
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { StockIndexChart } from './StockIndexChart';
import { TabPanelLoading } from './TabPanelLoading';

interface StockIndexTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function StockIndexTab({
  timeRange,
  onTimeRangeChange,
  refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
}: StockIndexTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="stock-indices" />
        <InitButton
          onInit={economicApi.initIndicesHistory}
          storageKey="last_initialized_macro_indices"
          label="初始化历史数据"
          hasData={!!fullData?.indices?.SPX?.length}
          onSuccess={onRefreshSuccess}
        />
        <RefreshButton
          onRefresh={economicApi.updateIndices}
          storageKey="last_updated_indices_daily"
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
          <StockIndexChart data={data} />
        </div>
      )}

      {isLoading && <TabPanelLoading message="加载股指数据中…" />}
    </div>
  );
}
