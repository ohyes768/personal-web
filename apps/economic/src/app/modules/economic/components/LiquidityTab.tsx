'use client';

/**
 * 流动性/风险 Tab — 容器组件
 * - 展示 VIX 恐慌指数 + TGA 账户余额 + HIBOR 隔夜拆息
 * - 每个数据源独立的 InitButton + RefreshButton（参考 CommodityTab 模板）
 * - 复用 useEconomicData hook（tabType='treasury-exchange' 保留所有字段含 vix/tga/hibor）
 * - 复用 TimeRangeSelector（liquidity-risk tabType 走 TREASURY_TIME_RANGES 默认）
 */
import { useState, useCallback } from 'react';
import type { TimeRange } from '@/lib/types/economic';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { LiquidityChart } from './LiquidityChart';

export function LiquidityTab() {
  const [timeRange, setTimeRange] = useState<TimeRange>('6M');
  const [refreshKey, setRefreshKey] = useState(0);

  // 复用 treasury-exchange tabType（filterDataByTab 对 liquidity-risk 走 fallthrough 返回 data 原样）
  const { data, isLoading, error, isCached } = useEconomicData(timeRange, 'treasury-exchange', refreshKey);

  const handleRefreshSuccess = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} tabType="liquidity-risk" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initVIXHistory}
          storageKey="last_initialized_macro_liquidity_vix"
          label="初始化 VIX"
          hasData={!!data?.vix?.length}
        />
        <RefreshButton
          onRefresh={economicApi.updateVIX}
          storageKey="last_updated_liquidity_vix_daily"
          cadence="daily"
          label="更新 VIX"
          onSuccess={handleRefreshSuccess}
        />
        <InitButton
          onInit={economicApi.initTGAHistory}
          storageKey="last_initialized_macro_liquidity_tga"
          label="初始化 TGA"
          hasData={!!data?.tga?.length}
        />
        <RefreshButton
          onRefresh={economicApi.updateTGA}
          storageKey="last_updated_liquidity_tga_daily"
          cadence="daily"
          label="更新 TGA"
          onSuccess={handleRefreshSuccess}
        />
        <InitButton
          onInit={economicApi.initHIBORHistory}
          storageKey="last_initialized_macro_liquidity_hibor"
          label="初始化 HIBOR"
          hasData={!!data?.hibor?.length}
        />
        <RefreshButton
          onRefresh={economicApi.updateHIBOR}
          storageKey="last_updated_liquidity_hibor_daily"
          cadence="daily"
          label="更新 HIBOR"
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
          <LiquidityChart data={data} />
        </div>
      )}

      {isLoading && (
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400">加载流动性/风险数据中...</p>
        </div>
      )}
    </div>
  );
}