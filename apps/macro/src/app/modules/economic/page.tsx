/**
 * 宏观经济数据页面 — 路由层
 * 数据获取：按 activeTab 用 useTabEconomicData 拉该 Tab 全历史并缓存；切时间周期仅本地切片
 * 渲染：各 Tab 始终挂载，用 hidden 控制显隐（state 持久、Plotly 不重建）
 * 子组件：按 timeRange + tabType 用 useFilteredEconomicData 拿自己需要的 data
 */
'use client';

import { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import type { TabType, TimeRange } from '@/lib/types/economic';
import { economicApi } from '@/lib/modules/economic/api';
import { useTabEconomicData } from '@/lib/hooks/useTabEconomicData';
import { Tabs } from './components/Tabs';

// 动态导入各 Tab 子组件（每个 Tab 自己的 hooks / 按钮 / 图表都在子组件里）
const TreasuryExchangeTab = dynamic(() => import('./components/TreasuryExchangeTab').then(mod => ({ default: mod.TreasuryExchangeTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载中美利差/汇率...</div>
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

const MacroSignalTab = dynamic(() => import('./components/MacroSignalTab').then(mod => ({ default: mod.MacroSignalTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载宏观信号...</div>
});

const MarketSentimentTab = dynamic(() => import('./components/MarketSentimentTab').then(mod => ({ default: mod.MarketSentimentTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载市场情绪...</div>
});

export default function EconomicPage() {
  const [activeTab, setActiveTab] = useState<TabType>('macro-signal');
  const [timeRange, setTimeRange] = useState<TimeRange>('3M');
  const [refreshKey, setRefreshKey] = useState(0);  // 数据刷新触发器

  // 按 Tab 拉全历史：切换 Tab 请求 /api/macro/data/{tab}，同 Tab 切时间周期不再请求
  const { tabDataMap, isLoading, error } = useTabEconomicData(activeTab, refreshKey);

  // 根据 Tab 类型自动切换默认时间范围
  const handleTabChange = useCallback((tabId: TabType) => {
    setActiveTab(tabId);
    // 中美利差/汇率默认 3M
    if (tabId === 'treasury-exchange' && timeRange === '1Y') {
      setTimeRange('3M');
    } else if (tabId === 'comparison' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'stock-indices' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'liquidity-risk' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'rates' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    } else if (tabId === 'market-sentiment' && (timeRange === '3M' || timeRange === '1Y')) {
      setTimeRange('6M');
    }
  }, [timeRange]);

  // 刷新成功后递增 refreshKey 触发当前 Tab 重新 fetch
  const handleRefreshSuccess = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  // Tab配置(信号首页 = 宏观信号,置首)
  const tabs: Array<{ id: TabType; label: string; description: string }> = [
    {
      id: 'macro-signal',
      label: '信号首页',
      description: '月度 6 维度宏观判断卡片 + 日频指标快照'
    },
    {
      id: 'treasury-exchange',
      label: '中美利差/汇率',
      description: '中美 10y 国债利差 + 汇率数据趋势分析（日级）'
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
    },
    {
      id: 'market-sentiment',
      label: '市场情绪',
      description: '两市成交额 + 换手率 + 融资余额（日级，由后端每日盘后调度追加）'
    }
  ];

  return (
    <main className="min-h-screen bg-black text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* 头部 */}
        <header className="mb-8">
          <div className="flex justify-between items-start mb-6">
            <div>
              {/* 原生 <a> 而非 Link：basePath=/macro 会把 Link 的 href 再拼一层 */}
              <a
                href="/"
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回首页
              </a>
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
            fullData={tabDataMap['treasury-exchange'] ?? null}
            isLoading={activeTab === 'treasury-exchange' && isLoading}
            error={error}
          />
        </div>
        <div hidden={activeTab !== 'comparison'}>
          <ComparisonTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            isActive={activeTab === 'comparison'}
          />
        </div>
        <div hidden={activeTab !== 'commodities'}>
          <CommodityTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={tabDataMap['commodities'] ?? null}
            isLoading={activeTab === 'commodities' && isLoading}
            error={error}
          />
        </div>
        <div hidden={activeTab !== 'stock-indices'}>
          <StockIndexTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={tabDataMap['stock-indices'] ?? null}
            isLoading={activeTab === 'stock-indices' && isLoading}
            error={error}
          />
        </div>
        <div hidden={activeTab !== 'liquidity-risk'}>
          <LiquidityTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={tabDataMap['liquidity-risk'] ?? null}
            isLoading={activeTab === 'liquidity-risk' && isLoading}
            error={error}
          />
        </div>
        <div hidden={activeTab !== 'rates'}>
          <RatesTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            refreshKey={refreshKey}
            onRefreshSuccess={handleRefreshSuccess}
            fullData={tabDataMap['rates'] ?? null}
            isLoading={activeTab === 'rates' && isLoading}
            error={error}
          />
        </div>
        <div hidden={activeTab !== 'macro-signal'}>
          {/* 模块级函数引用稳定：切 Tab 重渲染不会再打 /api/macro/signal */}
          <MacroSignalTab
            loadSnapshot={economicApi.getSignalSnapshot}
            onJumpToTab={setActiveTab}
          />
        </div>
        <div hidden={activeTab !== 'market-sentiment'}>
          <MarketSentimentTab
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            fullData={tabDataMap['market-sentiment'] ?? null}
            isLoading={activeTab === 'market-sentiment' && isLoading}
            error={error}
          />
        </div>
      </div>

      {/* 悬浮入口：右下角齿轮按钮，跳转定时任务管理页（/macro/scheduler） */}
      <Link
        href="/scheduler"
        aria-label="定时任务管理"
        title="定时任务管理"
        className="fixed bottom-6 right-6 z-50 w-12 h-12 flex items-center justify-center rounded-full bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors shadow-lg"
      >
        {/* 齿轮图标（内联 SVG，不引入图标库新依赖） */}
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M10.343 3.94c.09-.542.56-.94 1.113-.94h1.088c.553 0 1.023.398 1.113.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.09c0 .55-.397 1.02-.94 1.11l-.893.149c-.425.07-.765.383-.93.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.397.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.113.94h-1.088c-.553 0-1.023-.398-1.113-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.505-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.09c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.929-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z"
          />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </Link>
    </main>
  );
}
