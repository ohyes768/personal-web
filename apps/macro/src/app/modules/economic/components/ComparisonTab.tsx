'use client';

/**
 * 对比模块 — 容器组件
 * - 顶层 page.tsx 用 useFullEconomicData 拉一次全量数据，本组件接 props 拿 fullData
 * - useFilteredEconomicData 复用 'treasury-exchange' tabType（filterDataByTab 对此返 data 原样）
 * - 复用 TimeRangeSelector
 * - state: selectedIds（由 IndicatorSelector 管理，写 localStorage）+ viewMode（手动切换）
 */
import { useState } from 'react';
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { TimeRangeSelector } from './TimeRangeSelector';
import { IndicatorSelector } from './IndicatorSelector';
import { ComparisonChart } from './ComparisonChart';
import type { IndicatorId, ViewMode } from '@/lib/modules/comparison/types';

interface ComparisonTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
}

const VIEW_MODE_OPTIONS: Array<{ value: ViewMode; label: string; hint: string }> = [
  { value: 'minMax',                  label: '满幅对比',  hint: '每条线 min=0% max=100%，占画布 80% 高度（跨指标对比推荐）' },
  { value: 'normalize',               label: '归一化',    hint: '起点=100，对比相对涨跌（适合同质指标，如美债 2y + 10y）' },
  { value: 'dualAxis',                label: '双轴真实值', hint: '按单位分左右轴，看绝对水平' },
  { value: 'dualAxisWithCorrelation', label: '+相关性',   hint: '双轴 + 30 日滚动 Pearson 相关性（需选 2 个指标）' },
];

export function ComparisonTab({
  timeRange,
  onTimeRangeChange,
  refreshKey: _refreshKey,
  onRefreshSuccess: _onRefreshSuccess,
  fullData,
  isLoading,
  error,
}: ComparisonTabProps) {
  const [selectedIds, setSelectedIds] = useState<IndicatorId[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('minMax');

  const data = useFilteredEconomicData(fullData, timeRange, 'treasury-exchange');
  const correlationDisabled = selectedIds.length !== 2;

  return (
    <div className="space-y-6">
      <IndicatorSelector value={selectedIds} onChange={setSelectedIds} />

      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">视图：</span>
          <div className="inline-flex rounded-md border border-gray-700 overflow-hidden">
            {VIEW_MODE_OPTIONS.map((opt) => {
              const disabled = opt.value === 'dualAxisWithCorrelation' && correlationDisabled;
              const active = viewMode === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  disabled={disabled}
                  title={opt.hint}
                  onClick={() => setViewMode(opt.value)}
                  className={[
                    'px-3 py-1.5 text-sm transition-colors',
                    active
                      ? 'bg-blue-600 text-white'
                      : disabled
                        ? 'bg-gray-900 text-gray-600 cursor-not-allowed'
                        : 'bg-gray-900 text-gray-300 hover:bg-gray-800 hover:text-white',
                  ].join(' ')}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          {viewMode === 'dualAxisWithCorrelation' && correlationDisabled && (
            <span className="text-xs text-amber-400">需选恰好 2 个指标</span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-gray-400">时间范围：</span>
          <TimeRangeSelector value={timeRange} onChange={onTimeRangeChange} tabType="comparison" />
        </div>
      </div>

      {error && (
        <div className="p-6 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-200 mb-2">获取数据失败</p>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {data && !isLoading && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <ComparisonChart selectedIds={selectedIds} data={data} viewMode={viewMode} />
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
