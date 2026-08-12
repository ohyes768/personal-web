'use client';

/**
 * 商品 Tab — 容器组件
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType（filterDataByTab 对 commodities 不裁剪）
 * - 复用 TimeRangeSelector
 * - 复用 RefreshButton（commodities 是日级，cadence=daily）
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { CommodityChart } from './CommodityChart';

interface CommodityTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function CommodityTab({
  timeRange,
  onTimeRangeChange,
  refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: CommodityTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="commodities" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initCommoditiesHistory}
          storageKey="last_initialized_macro_commodities"
          label="初始化商品数据"
          hasData={!!data?.commodities?.gold?.length}
        />
        <RefreshButton
          onRefresh={economicApi.updateCommodities}
          storageKey="last_updated_commodities_daily"
          cadence="daily"
          label="更新商品"
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
          <CommodityChart data={data} />
        </div>
      )}

      {isLoading && (
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400">加载商品数据中...</p>
        </div>
      )}
    </div>
  );
}