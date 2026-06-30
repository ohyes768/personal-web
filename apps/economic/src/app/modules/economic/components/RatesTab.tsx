'use client';

/**
 * 利率利差 Tab — 容器组件
 * - 展示 SOFR + 美债3M + TED 利差 + 中国10y + 中国10年-2年
 * - 数据源独立 InitButton + RefreshButton（参考 LiquidityTab 模板）
 * - 复用 useEconomicData hook（tabType='treasury-exchange' 保留所有字段含 ted_spread/china_bond）
 * - 复用 TimeRangeSelector（rates tabType 走 TREASURY_TIME_RANGES 默认）
 */
import { useState, useCallback } from 'react';
import type { TimeRange } from '@/lib/types/economic';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { RatesChart } from './RatesChart';

export function RatesTab() {
  const [timeRange, setTimeRange] = useState<TimeRange>('6M');
  const [refreshKey, setRefreshKey] = useState(0);

  // 复用 treasury-exchange tabType（filterDataByTab 对 rates 走 fallthrough 返回 data 原样）
  const { data, isLoading, error, isCached } = useEconomicData(timeRange, 'treasury-exchange', refreshKey);

  const handleRefreshSuccess = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} tabType="rates" />
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