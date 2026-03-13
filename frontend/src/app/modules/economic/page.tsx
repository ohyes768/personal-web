/**
 * 宏观经济数据页面
 */
'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import type { TimeRange } from '@/lib/types/economic';
import type { TimeRange as FundFlowTimeRange, ChartData as FundFlowChartData } from '@/lib/modules/fund-flow/types';
import { useEconomicData } from '@/lib/hooks/useEconomicData';
import { TimeRangeSelector } from './components/TimeRangeSelector';
import { LoadingOverlay } from './components/LoadingOverlay';
import { Tabs } from './components/Tabs';
import { IndicatorCards } from '@/components/modules/fund-flow/IndicatorCards';
import { TimeRangeSelector as FundFlowTimeRangeSelector } from '@/components/modules/fund-flow/TimeRangeSelector';
import { getHistoryData, getCumulativeData } from '@/lib/modules/fund-flow/api';

// 动态导入图表组件，禁用SSR
const EconomicChart = dynamic(() => import('./components/EconomicChart').then(mod => ({ default: mod.EconomicChart })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载图表中...</div>
});

const BondChart = dynamic(() => import('./components/BondChart').then(mod => ({ default: mod.BondChart })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载图表中...</div>
});

// 动态导入资金流向图表组件
const FundFlowChart = dynamic(() => import('@/components/modules/fund-flow/FundFlowChart').then(mod => ({ default: mod.FundFlowChart })), {
  ssr: false,
  loading: () => <div className="h-[500px] flex items-center justify-center text-gray-400">加载图表中...</div>
});

// Tab类型定义
type TabType = 'treasury-exchange' | 'bonds' | 'fund-flow';

export default function EconomicPage() {
  const [activeTab, setActiveTab] = useState<TabType>('treasury-exchange');
  const [timeRange, setTimeRange] = useState<TimeRange>('3M');
  const [fundFlowTimeRange, setFundFlowTimeRange] = useState<FundFlowTimeRange>('ALL');
  const [fundFlowData, setFundFlowData] = useState<FundFlowChartData[]>([]);
  const [cumulativeData, setCumulativeData] = useState<Awaited<ReturnType<typeof getCumulativeData>> | null>(null);
  const [fundFlowLoading, setFundFlowLoading] = useState(false);
  const [fundFlowError, setFundFlowError] = useState<string | null>(null);

  // 根据 Tab 类型自动切换默认时间范围
  const handleTabChange = useCallback((tabId: TabType) => {
    setActiveTab(tabId);
    // 美债汇率默认 3M，德债日债默认 1Y
    if (tabId === 'bonds' && timeRange === '3M') {
      setTimeRange('1Y');
    } else if (tabId === 'treasury-exchange' && timeRange === '1Y') {
      setTimeRange('3M');
    }
  }, [timeRange]);

  // 获取资金流向数据
  const fetchFundFlowData = useCallback(async () => {
    try {
      setFundFlowLoading(true);
      setFundFlowError(null);

      const [history, cumulative] = await Promise.all([
        getHistoryData(),
        getCumulativeData(),
      ]);

      setFundFlowData(history);
      setCumulativeData(cumulative);
    } catch (err) {
      console.error('Failed to fetch fund flow data:', err);
      setFundFlowError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setFundFlowLoading(false);
    }
  }, []);

  // 首次加载时获取资金流向数据
  useEffect(() => {
    fetchFundFlowData();
  }, [fetchFundFlowData]);

  // 获取经济数据
  const { data, isLoading, error, isCached } = useEconomicData(timeRange, activeTab);

  // 生成图表组件的 key，确保数据变化时重新挂载组件
  const chartKey = useMemo(() => {
    if (!data || data.dates.length === 0) return 'empty';
    const firstDate = data.dates[0] || '';
    const lastDate = data.dates[data.dates.length - 1] || '';
    return firstDate + '-' + lastDate;
  }, [data]);

  // Tab配置
  const tabs: Array<{ id: TabType; label: string; description: string }> = [
    {
      id: 'treasury-exchange',
      label: '美债汇率',
      description: '美国国债收益率与汇率数据趋势分析（日级）'
    },
    {
      id: 'bonds',
      label: '德债日债',
      description: '德国和日本国债收益率对比分析（月级，每月1号数据）'
    },
    {
      id: 'fund-flow',
      label: '资金流向',
      description: '沪深港通北向/南向资金流向数据（日级）'
    }
  ];

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
            </div>
          </div>
        </header>

        {/* Tab组件 */}
        <Tabs
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={handleTabChange}
        />

        {/* 经济数据 Tab 的时间范围选择器 */}
        {activeTab !== 'fund-flow' && (
          <div className="flex items-center gap-6 mb-8">
            <span className="text-gray-400">时间范围：</span>
            <TimeRangeSelector value={timeRange} onChange={setTimeRange} tabType={activeTab} />
            {isCached && (
              <span className="text-sm text-gray-500">（缓存）</span>
            )}
          </div>
        )}

        {/* 错误提示 - 经济数据 */}
        {error && activeTab !== 'fund-flow' && (
          <div className="mb-8 p-6 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-red-200 mb-2">获取数据失败</p>
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* 错误提示 - 资金流向 */}
        {fundFlowError && activeTab === 'fund-flow' && (
          <div className="mb-8 p-6 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-red-200 mb-2">获取数据失败</p>
            <p className="text-red-400 text-sm">{fundFlowError}</p>
          </div>
        )}

        {/* 经济数据图表 */}
        {data && !isLoading && activeTab !== 'fund-flow' && (
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            {/* 美债汇率 Tab */}
            {activeTab === 'treasury-exchange' && (
              <EconomicChart key={`treasury-${chartKey}`} data={data} showAllData={false} />
            )}

            {/* 德债日债 Tab */}
            {activeTab === 'bonds' && (
              <BondChart key={`bonds-${chartKey}`} data={data} />
            )}
          </div>
        )}

        {/* 资金流向 Tab */}
        {activeTab === 'fund-flow' && (
          <>
            {/* 指标卡片 */}
            <IndicatorCards data={cumulativeData} />

            {/* 时间范围选择器 */}
            <div className="flex items-center gap-6 mb-6">
              <span className="text-gray-400">时间范围：</span>
              <FundFlowTimeRangeSelector value={fundFlowTimeRange} onChange={setFundFlowTimeRange} />
            </div>

            {/* 图表 */}
            <FundFlowChart data={fundFlowData} timeRange={fundFlowTimeRange} />
          </>
        )}

        {/* 空状态 */}
        {!isLoading && !fundFlowLoading && !data && !error && !fundFlowError && activeTab !== 'fund-flow' && (
          <div className="text-center py-20">
            <p className="text-gray-400 text-lg">暂无数据</p>
          </div>
        )}

        {/* 加载遮罩 */}
        {(isLoading || fundFlowLoading) && <LoadingOverlay message="加载经济数据中..." />}
      </div>
    </main>
  );
}