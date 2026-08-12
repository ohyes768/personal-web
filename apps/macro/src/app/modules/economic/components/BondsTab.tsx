'use client';

/**
 * 德债日债 Tab — 容器组件
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 走 'bonds' tabType 内部自动调 filterMonthlyData 月级切分
 * - 复用 TimeRangeSelector / InitButton / RefreshButton（cadence=monthly）
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
import { BondChart } from './BondChart';

interface BondsTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function BondsTab({
  timeRange,
  onTimeRangeChange,
  refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: BondsTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'bonds');

  const handleRefreshSuccess = useCallback(() => onRefreshSuccess(), [onRefreshSuccess]);

  // 生成图表组件的 key，确保数据变化时重新挂载组件
  const chartKey = useMemo(() => buildChartKey(data), [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 mb-8 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="bonds" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initBondsHistory}
          storageKey="last_initialized_macro_bonds"
          label="初始化德债/日债"
          hasData={!!data && data.dates && data.dates.length > 0}
        />
        <RefreshButton
          onRefresh={economicApi.updateBonds}
          storageKey="last_updated_bonds"
          cadence="monthly"
          label="更新德债/日债"
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
          <BondChart key={`bonds-${chartKey}`} data={data} />
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
