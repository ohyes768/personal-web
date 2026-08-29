'use client';

/**
 * 对比模块 — 容器组件
 * - 按 selectedIds 请求 GET /api/macro/data/comparison?indicators=
 * - 缓存 key = 排序后的 id 列表；子集且未过 TTL 不重拉；超集带 loading 重拉
 */
import { useState, useEffect, useRef } from 'react';
import type { TimeRange, EconomicDataResponse } from '@/lib/types/economic';
import { useFilteredEconomicData } from '@/lib/hooks/useFilteredEconomicData';
import { economicApi } from '@/lib/modules/economic/api';
import { TimeRangeSelector } from './TimeRangeSelector';
import { IndicatorSelector } from './IndicatorSelector';
import { ComparisonChart } from './ComparisonChart';
import { TabPanelLoading } from './TabPanelLoading';
import type { IndicatorId, ViewMode } from '@/lib/modules/comparison/types';
import { DEFAULT_INDICATORS } from '@/lib/modules/comparison/indicators';

interface ComparisonTabProps {
  timeRange: TimeRange;
  onTimeRangeChange: (value: TimeRange) => void;
  refreshKey: number;
  onRefreshSuccess: () => void;
  /** 仅当前 Tab 可见时才请求，避免始终挂载导致首屏就打 comparison */
  isActive: boolean;
}

const VIEW_MODE_OPTIONS: Array<{ value: ViewMode; label: string; hint: string }> = [
  { value: 'minMax',                  label: '满幅对比',  hint: '每条线 min=0% max=100%，占画布 80% 高度（跨指标对比推荐）' },
  { value: 'normalize',               label: '归一化',    hint: '起点=100，对比相对涨跌（适合同质指标，如美债 2y + 10y）' },
  { value: 'dualAxis',                label: '双轴真实值', hint: '按单位分左右轴，看绝对水平' },
  { value: 'dualAxisWithCorrelation', label: '+相关性',   hint: '双轴 + 30 日滚动 Pearson 相关性（需选 2 个指标）' },
];

const COMPARISON_TTL_MS = 5 * 60 * 1000;

type ComparisonCacheEntry = { data: EconomicDataResponse; fetchedAt: number };

function idsKey(ids: IndicatorId[]): string {
  return [...ids].sort().join(',');
}

export function ComparisonTab({
  timeRange,
  onTimeRangeChange,
  refreshKey,
  onRefreshSuccess: _onRefreshSuccess,
  isActive,
}: ComparisonTabProps) {
  const [selectedIds, setSelectedIds] = useState<IndicatorId[]>(DEFAULT_INDICATORS);
  const [viewMode, setViewMode] = useState<ViewMode>('minMax');
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cacheRef = useRef<Map<string, ComparisonCacheEntry>>(new Map());
  const lastRefreshKeyRef = useRef(refreshKey);

  const resolvedIds = selectedIds.length > 0 ? selectedIds : DEFAULT_INDICATORS;
  const key = idsKey(resolvedIds);

  useEffect(() => {
    if (!isActive) {
      // 别的 Tab 点更新会 bump 全局 refreshKey；对比未可见时只同步 ref，不清缓存
      lastRefreshKeyRef.current = refreshKey;
      return;
    }

    const ids = key.split(',') as IndicatorId[];
    let cancelled = false;

    if (refreshKey !== lastRefreshKeyRef.current) {
      lastRefreshKeyRef.current = refreshKey;
      cacheRef.current.delete(key);
    }

    const now = Date.now();
    for (const [cachedKey, entry] of cacheRef.current) {
      if (now - entry.fetchedAt > COMPARISON_TTL_MS) continue;
      const cachedIds = cachedKey.split(',');
      if (ids.every((id) => cachedIds.includes(id))) {
        setFullData(entry.data);
        setIsLoading(false);
        setError(null);
        return;
      }
    }

    setIsLoading(true);
    setError(null);

    economicApi
      .getComparisonData(ids)
      .then((data) => {
        if (cancelled) return;
        cacheRef.current.set(key, { data, fetchedAt: Date.now() });
        setFullData(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : '获取数据失败');
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [key, refreshKey, isActive]);

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

      {isLoading && <TabPanelLoading message="加载对比数据中…" />}

      {data && !isLoading && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <ComparisonChart selectedIds={selectedIds} data={data} viewMode={viewMode} />
        </div>
      )}
    </div>
  );
}
