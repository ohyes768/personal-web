/**
 * 资金流向页面
 * 展示沪深港通北向/南向资金流向数据
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { FundFlowChart } from '@/components/modules/fund-flow/FundFlowChart';
import { IndicatorCards } from '@/components/modules/fund-flow/IndicatorCards';
import { TimeRangeSelector } from '@/components/modules/fund-flow/TimeRangeSelector';
import { getCumulativeData, getHistoryData, updateData } from '@/lib/modules/fund-flow/api';
import type { CumulativeData, ChartData, TimeRange } from '@/lib/modules/fund-flow/types';

export default function FundFlowPage() {
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [cumulativeData, setCumulativeData] = useState<CumulativeData | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取数据
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 并行获取累计数据和历史数据
      const [cumulative, history] = await Promise.all([
        getCumulativeData(),
        getHistoryData(),
      ]);

      setCumulativeData(cumulative);
      setChartData(history);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 手动刷新
  const handleRefresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 先触发后端更新
      await updateData();

      // 重新获取数据
      await fetchData();
    } catch (err) {
      console.error('Failed to refresh data:', err);
      setError(err instanceof Error ? err.message : '刷新失败');
    } finally {
      setLoading(false);
    }
  }, [fetchData]);

  // 页面加载时获取数据
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 骨架屏
  if (loading && chartData.length === 0) {
    return (
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
        <div className="mb-6">
          <div className="h-8 bg-[#1e222d] rounded w-48 mb-2 animate-pulse"></div>
          <div className="h-5 bg-[#1e222d] rounded w-32 animate-pulse"></div>
        </div>
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-[#1e222d] rounded-lg p-6 h-32 animate-pulse"></div>
          ))}
        </div>
        <div className="bg-[#1e222d] rounded-lg h-[500px] animate-pulse"></div>
      </div>
    );
  }

  // 错误状态
  if (error && chartData.length === 0) {
    return (
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
        <div className="mb-6">
          <Link href="/" className="text-[#787b86] hover:text-white transition-colors">
            ← 返回首页
          </Link>
          <h1 className="text-4xl font-bold mt-4 text-[#d1d4dc]">资金流向</h1>
        </div>
        <div className="text-center py-16">
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={handleRefresh}
            className="px-6 py-2 bg-[#2962ff] text-white rounded hover:bg-[#1e54d8] transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
      {/* 头部导航 */}
      <div className="mb-6">
        <div className="flex justify-between items-start">
          <div>
            <Link href="/" className="text-[#787b86] hover:text-white transition-colors">
              ← 返回首页
            </Link>
            <h1 className="text-4xl font-bold mt-4 text-[#d1d4dc]">资金流向</h1>
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className={`
              px-4 py-2 rounded font-medium transition-all flex items-center gap-2
              ${loading
                ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
                : 'bg-[#2962ff] text-white hover:bg-[#1e54d8]'
              }
            `}
          >
            <svg
              className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            刷新
          </button>
        </div>
      </div>

      {/* 错误提示（有数据时） */}
      {error && chartData.length > 0 && (
        <div className="mb-4 bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 指标卡片 */}
      <IndicatorCards data={cumulativeData} />

      {/* 时间范围选择器 */}
      <TimeRangeSelector value={timeRange} onChange={setTimeRange} />

      {/* 图表 */}
      <FundFlowChart data={chartData} timeRange={timeRange} />
    </div>
  );
}