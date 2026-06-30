/**
 * 宏观经济数据页面 — 路由层
 * 数据获取：顶层 useFullEconomicData 拉一次，所有 Tab 共享 fullData
 * 渲染：7 个 Tab 始终挂载，用 hidden 控制显隐（state 持久、Plotly 不重建）
 * 子组件：按 timeRange + tabType 用 useFilteredEconomicData 拿自己需要的 data
 */
'use client';

import { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import type { TabType, TimeRange } from '@/lib/types/economic';
import { useFullEconomicData } from '@/lib/hooks/useFullEconomicData';
import { Tabs } from './components/Tabs';

// 动态导入各 Tab 子组件（每个 Tab 自己的 hooks / 按钮 / 图表都在子组件里）
const TreasuryExchangeTab = dynamic(() => import('./components/TreasuryExchangeTab').then(mod => ({ default: mod.TreasuryExchangeTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载中美利差/汇率...</div>
});

const BondsTab = dynamic(() => import('./components/BondsTab').then(mod => ({ default: mod.BondsTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载德债日债...</div>
});

const ComparisonTab = dynamic(() => import('./components/ComparisonTab').then(mod => ({ default: mod.ComparisonTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载对比模块...</div>
});

const CommodityTab = dynamic(() => import('./components/CommodityTab').then(mod => ({ default: mod.CommodityTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载商品模块...</div>
});

const StockIndexTab = dynamic(() => import('./components/StockIndexTab').then(mod => ({ default: mod.StockIndexTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载股指模块...</div>
});

const LiquidityTab = dynamic(() => import('./components/LiquidityTab').then(mod => ({ default: mod.LiquidityTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载流动性/风险模块...</div>
});

const RatesTab = dynamic(() => import('./components/RatesTab').then(mod => ({ default: mod.RatesTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载利率利差模块...</div>
});

export default function EconomicPage() {
  const [activeTab, setActiveTab] = useState<TabType>('treasury-exchange');
  const [timeRange, setTimeRange] = useState<TimeRange>('3M');
  const [refreshKey, setRefreshKey] = useState(0);  // 数据刷新触发器

  // 顶层只调一次：所有 Tab 共享同一份 fullData + loading/error/isCached
  const { fullData, isLoading, error, isCached } = useFullEconomicData(refreshKey);

  // 根据 Tab 类型自动切换默认时间范围
  const handleTabChange = useCallback((tabId: TabType) => {
    setActiveTab(tabId);
    // 中美利差/汇率默认 3M，德债日债默认 1Y
    if (tabId === 'bonds' && timeRange === '3M') {
      setTimeRange('1Y');
    } else if (tabId === 'treasury-exchange' && timeRange === '1Y') {
      setTimeRange('3M');
    } else if (tabId === 'comparison' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'stock-indices' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'liquidity-risk' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'rates' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    }
  }, [timeRange]);

  // 刷新成功后递增 refreshKey 触发顶层 useFullEconomicData 重新 fetch
  const handleRefreshSuccess = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  // Tab配置
  const tabs: Array<{ id: TabType; label: string; description: string }> = [
    {
      id: 'treasury-exchange',
      label: '中美利差/汇率',
      description: '中美 10y 国债利差 + 汇率数据趋势分析（日级）'
    },
    {
      id: 'bonds',
      label: '德债日债',
      description: '德国和日本国债收益率对比分析（月级，每月1号数据）'
    },
    {
      id: 'liquidity-risk',
      label: '流动性/风险',
      description: 'VIX 恐慌指数 + TGA 账户余额 + HIBOR 隔夜拆息走势（日级）'
    },
    {
      id: 'rates',
      label: '利率利差',
      description: 'SOFR + 美债3M + TED利差 + 中国10y + 中国10年-2年（同图 4 轴叠加，日级）'
    },
    {
      id: 'comparison',
      label: '对比',
      description: '多指标归一化对比分析（2-6 条曲线叠加）'
    },
    {
      id: 'commodities',
      label: '商品',
      description: '黄金/白银/原油/铜价格曲线（黄金白银左轴，原油铜右轴）'
    },
    {
      id: 'stock-indices',
      label: '股指',
      description: '恒生/上证/标普500/纳指/道琼斯日 K 线（5 轴叠加）'
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
                href="/economic"
                className="text-gray-400 hover:text-white transition-colors"
              >
                刷新
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

        {/* 各 Tab 子组件：始终挂载，仅用 hidden 控制显隐 — state 持久，Plotly 不重建 */}
        <div hidden={activeTab !== 'treasury-exchange'}>
          <TreasuryExchangeTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'bonds'}>
          <BondsTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'comparison'}>
          <ComparisonTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'commodities'}>
          <CommodityTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'stock-indices'}>
          <StockIndexTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'liquidity-risk'}>
          <LiquidityTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'rates'}>
          <RatesTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={fullData}
            isLoading={isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
      </div>
    </main>
  );
}
