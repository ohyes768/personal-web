'use client';

/**
 * 流动性/风险 Tab — 容器组件
 * - 展示 VIX 恐慌指数 + TGA 账户余额 + HIBOR 隔夜拆息
 * - 1 个「初始化」+ 1 个「更新数据」按钮（合并原 VIX/TGA/HIBOR 三套独立按钮），
 *   内部并发调 3 个端点（economicApi.initLiquidityHistory / updateLiquidity）
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType（filterDataByTab 对 liquidity-risk 走 fallthrough 返回 data 原样）
 * - 复用 TimeRangeSelector（liquidity-risk tabType 走 TREASURY_TIME_RANGES 默认）
 * - onSuccess 用顶层 onRefreshSuccess prop，触发 page.tsx refreshKey++，
 *   顶层 hook 重新 fetch，**所有 Tab 数据同步更新**
 */
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { RefreshButton } from './RefreshButton';
import { InitButton } from './InitButton';
import { LiquidityChart } from './LiquidityChart';

interface LiquidityTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

export function LiquidityTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess,
  fullData,
  isLoading,
  error,
  isCached,
}: LiquidityTabProps) {
  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 flex-wrap">
        <span className="text-gray-400">时间范围：</span>
        <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="liquidity-risk" />
        {isCached && <span className="text-sm text-gray-500">（缓存）</span>}
        <InitButton
          onInit={economicApi.initLiquidityHistory}
          storageKey="last_initialized_macro_liquidity"
          label="初始化流动性/风险"
          hasData={!!(data?.vix?.length && data?.tga?.length && data?.hibor?.length)}
        />
        <RefreshButton
          onRefresh={economicApi.updateLiquidity}
          storageKey="last_updated_liquidity_daily"
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