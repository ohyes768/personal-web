'use client';

/**
 * 对比模块 — 容器组件
 * - 复用 useEconomicData hook（tabType='treasury-exchange' 保留所有字段）
 * - 复用 TimeRangeSelector
 * - state: selectedIds（由 IndicatorSelector 管理，写 localStorage）
 */
import { useState } from 'react';
import type { TimeRange } from '@/lib/types/economic';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { TimeRangeSelector } from './TimeRangeSelector';
import { IndicatorSelector } from './IndicatorSelector';
import { ComparisonChart } from './ComparisonChart';
import type { IndicatorId } from '@/lib/modules/comparison/types';

export function ComparisonTab() {
  const [timeRange, setTimeRange] = useState<TimeRange>('6M');
  const [selectedIds, setSelectedIds] = useState<IndicatorId[]>([]);

  // 复用现有 hook：用 'treasury-exchange' tabType（filterDataByTab 对此返 data 原样，含所有可选字段）
  const { data, isLoading, error, isCached } = useEconomicData(timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <IndicatorSelector value={selectedIds} onChange={setSelectedIds} />

      <div className="flex items-center gap-6">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} tabType="comparison" />
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
