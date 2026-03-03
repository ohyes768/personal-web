/**
 * 宏观经济数据页面
 */
'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import type { TimeRange } from '@/lib/types/economic';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { TimeRangeSelector } from './components/TimeRangeSelector';
import { LoadingOverlay } from './components/LoadingOverlay';

// 动态导入图表组件，禁用SSR
const EconomicChart = dynamic(() => import('./components/EconomicChart').then(mod => ({ default: mod.EconomicChart })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载图表中...</div>
});

export default function EconomicPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>('3M');
  const { data, isLoading, error, isCached } = useEconomicData(timeRange);

  return (
    <main className="min-h-screen bg-black text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* 头部 */}
        <header className="mb-8">
          <div className="flex justify-between items-start mb-6">
            <div>
              <Link
                href="/"
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4">宏观经济数据</h1>
              <p className="text-gray-400 mt-2">
                美国国债收益率与汇率数据趋势分析
              </p>
            </div>
          </div>

          {/* 时间范围选择器 */}
          <div className="flex items-center gap-6">
            <span className="text-gray-400">时间范围：</span>
            <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
            {isCached && (
              <span className="text-sm text-gray-500">（缓存）</span>
            )}
          </div>
        </header>

        {/* 错误提示 */}
        {error && (
          <div className="mb-8 p-6 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-red-200 mb-2">获取数据失败</p>
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* 图表 */}
        {data && !isLoading && (
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <EconomicChart data={data} />
          </div>
        )}

        {/* 空状态 */}
        {!isLoading && !data && !error && (
          <div className="text-center py-20">
            <p className="text-gray-400 text-lg">暂无数据</p>
          </div>
        )}

        {/* 加载遮罩 */}
        {isLoading && <LoadingOverlay message="加载经济数据中..." />}
      </div>
    </main>
  );
}
