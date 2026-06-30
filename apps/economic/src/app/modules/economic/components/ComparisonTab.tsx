'use client';

/**
 * 对比模块 — 容器组件
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType（filterDataByTab 对此返 data 原样）
 * - 复用 TimeRangeSelector
 * - state: selectedIds（由 IndicatorSelector 管理，写 localStorage）
 */
import { useState } from 'react';
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { TimeRangeSelector } from './TimeRangeSelector';
import { IndicatorSelector } from './IndicatorSelector';
import { ComparisonChart } from './ComparisonChart';
import type { IndicatorId } from '@/lib/modules/comparison/types';

interface ComparisonTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function ComparisonTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess: _onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: ComparisonTabProps) {
  const [selectedIds, setSelectedIds] = useState<IndicatorId[]>([]);

  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <IndicatorSelector value={selectedIds} onChange={setSelectedIds} />

      <div className="flex items-center gap-6">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="comparison" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
      </div>

      {error && (
        <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">获取数据失败</p>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {data && !isLoading && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <ComparisonChart selectedIds={selectedIds} data={data} />
        </div>
      )}

      {isLoading && (
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400">加载经济数据中...</p>
        </div>
      )}
    </div>
  );
}
