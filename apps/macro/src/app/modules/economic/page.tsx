/**
 * 宏观经济数据页面 — 路由层
 * 数据获取：按 activeTab 用 useTabEconomicData 拉该 Tab 全历史并缓存；切时间周期仅本地切片
 * 渲染：7 个 Tab 始终挂载，用 hidden 控制显隐（state 持久、Plotly 不重建）
 * 子组件：按 timeRange + tabType 用 useFilteredEconomicData 拿自己需要的 data
 */
'use client';

import { useState, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import type { TabType, TimeRange } from '@/lib/types/economic';
import type { MacroSignalSnapshot } from '@/lib/modules/macro-signal/types';
import { useTabEconomicData } from '@/lib/hooks/useTabEconomicData';
import { loadMockSnapshot, MOCK_AVAILABLE_MONTHS } from '@/lib/modules/macro-signal/mock-data';
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

const MacroSignalTab = dynamic(() => import('./components/MacroSignalTab').then(mod => ({ default: mod.MacroSignalTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载宏观信号...</div>
});

export default function EconomicPage() {
  const [activeTab, setActiveTab] = useState<TabType>('treasury-exchange');
  const [timeRange, setTimeRange] = useState<TimeRange>('3M');
  const [refreshKey, setRefreshKey] = useState(0);  // 数据刷新触发器

  // 按 Tab 拉全历史：切换 Tab 请求 /api/macro/data/{tab}，同 Tab 切时间周期不再请求
  const { tabDataMap, isLoading, error, isCached } = useTabEconomicData(activeTab, refreshKey);

  // === 宏观信号数据源 ===
  // 本地开发(NODE_ENV === 'development')用 mock;线上(NODE_ENV === 'production')走真实接口
  // (线上接口当前未接入,后续 agent 实现后只需保证 /api/macro/signal 与 /api/macro/months 返回正确 shape 即可)
  const useMock = process.env.NODE_ENV !== 'production';
  const loadSnapshot = useMock
    ? loadMockSnapshot
    : async (month: string): Promise<MacroSignalSnapshot | null> => {
        const res = await fetch(`/api/macro/signal?month=${encodeURIComponent(month)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // 后端 MacroSignalResponse 是 { success, data } 包装,前端契约只要 data
        const body = await res.json() as { success?: boolean; data?: MacroSignalSnapshot };
        return body?.data ?? null;
      };
  const [availableMonths, setAvailableMonths] = useState<string[]>(
    useMock ? MOCK_AVAILABLE_MONTHS : []
  );
  useEffect(() => {
    if (useMock) return;
    fetch('/api/macro/months')
      .then(r => (r.ok ? r.json() : { months: [] }))
      .then(d => setAvailableMonths(Array.isArray(d?.months) ? d.months : []))
      .catch(() => { /* 接口未接入时保持空数组,MacroSignalTab 会显示 loading/error */ });
  }, [useMock]);

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
    },
    {
      id: 'macro-signal',
      label: '宏观信号',
      description: '当月 6 维度宏观判断卡片 + 发布日历'
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
                href="/macro"
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
            fullData={tabDataMap['treasury-exchange'] ?? null}
            isLoading={activeTab === 'treasury-exchange' && isLoading}
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
            fullData={tabDataMap['bonds'] ?? null}
            isLoading={activeTab === 'bonds' && isLoading}
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
            fullData={tabDataMap['comparison'] ?? null}
            isLoading={activeTab === 'comparison' && isLoading}
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
            fullData={tabDataMap['commodities'] ?? null}
            isLoading={activeTab === 'commodities' && isLoading}
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
            fullData={tabDataMap['stock-indices'] ?? null}
            isLoading={activeTab === 'stock-indices' && isLoading}
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
            fullData={tabDataMap['liquidity-risk'] ?? null}
            isLoading={activeTab === 'liquidity-risk' && isLoading}
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
            fullData={tabDataMap['rates'] ?? null}
            isLoading={activeTab === 'rates' && isLoading}
            error={error}
            isCached={isCached}
          />
        </div>
        <div hidden={activeTab !== 'macro-signal'}>
          <MacroSignalTab
            loadSnapshot={loadSnapshot}
            availableMonths={availableMonths}
            onJumpToTab={setActiveTab}
          />
        </div>
      </div>
    </main>
  );
}
