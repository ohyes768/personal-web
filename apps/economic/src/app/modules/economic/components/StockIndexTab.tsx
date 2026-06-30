'use client';

/**
 * 股指 Tab — 容器组件
 * - 复用 useEconomicData hook（tabType='treasury-exchange' 保留所有字段含 indices）
 * - 复用 TimeRangeSelector
 * - 复用 RefreshButton（indices 是日级 K 线，cadence=daily）
 * - 复用 InitButton（首次部署用 fetch/indices/history）
 */
import { useState, useCallback } from 'react';
import type { TimeRange } from '@/lib/types/economic';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { StockIndexChart } from './StockIndexChart';

export function StockIndexTab() {
  const [timeRange, setTimeRange] = useState<TimeRange>('6M');
  const [refreshKey, setRefreshKey] = useState(0);

  // 复用 treasury-exchange tabType（filterDataByTab 对 stock-indices 不裁剪）
  const { data, isLoading, error, isCached } = useEconomicData(timeRange, 'treasury-exchange', refreshKey);

  const handleRefreshSuccess = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} tabType="stock-indices" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initIndicesHistory}
          storageKey="last_initialized_macro_indices"
          label="初始化股指数据"
          hasData={!!data?.indices?.SPX?.length}
        />
        <RefreshButton
          onRefresh={economicApi.updateIndices}
          storageKey="last_updated_indices_daily"
          cadence="daily"
          label="更新股指"
          onSuccess={handleRefreshSuccess}
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

      {isLoading && (
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400">加载股指数据中...</p>
        </div>
      )}
    </div>
  );
}
