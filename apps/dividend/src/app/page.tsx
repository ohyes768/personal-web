/**
 * 股息率页面
 * 展示高股息率股票列表及技术指标
 */
'use client';

import { Suspense, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { StarIcon as StarIconOutline } from '@heroicons/react/24/outline';
import { DividendTable } from '@/components/DividendTable';
import { DetailModal } from '@/components/DetailModal';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { CompareDrawer } from '@/components/CompareDrawer';
import { AlertSettingsModal } from '@/components/AlertSettingsModal';
import { AlertLevelBar } from '@/components/AlertLevelBar';
import { SchedulerSettingsModal } from '@/components/SchedulerSettingsModal';
import { useDividendData, useTechnicalData, useDetailModal, useCompare, useDataUpdate } from '@/lib/hooks';
import { useWatchlist } from '@/lib/hooks/useWatchlist';
import { useAlertsStatus } from '@/lib/hooks/useAlertsStatus';
import { dividendApi } from '@/lib/api';
import type { DividendStock, DividendStockWithTechnical, AlertConfigRequest, AlertStatusItem, AlertLevels, IndexRefreshItem, HoldingsStatus } from '@/lib/types';

const MAX_COMPARE_SELECT = 5;
type TabKey = 'all' | 'watchlist' | 'alerts';

/**
 * 红利指数徽章白名单（与 fetcher.py 的 DIVIDEND_INDEXES + ALT_API_INDEXES 对齐）
 * 注意：932315 名为"中证红利质量"、931468 名为"红利质量"——徽章只展示 code 避免歧义，
 * hover tooltip 显示完整 name（来自后端）
 */
const CORE_DIVIDEND_INDEXES: { code: string; label: string }[] = [
  // 核心 4 个（中证系列，csindex 接口）
  { code: '000922', label: '000922' },
  { code: '932315', label: '932315' },
  { code: '932309', label: '932309' },
  { code: '931468', label: '931468' },
  // 扩展 4 个
  { code: '000015', label: '000015' },  // 上证红利，csindex
  { code: '000825', label: '000825' },  // 中证系列，csindex（名称待确认）
  { code: 'H30089', label: 'H30089' },  // 国证系列，ak.index_stock_cons
  { code: '399324', label: '399324' },  // 深证红利，ak.index_stock_cons
];

/**
 * 红利指数持仓刷新状态下拉面板
 * 触发按钮：「指数状态 X/Y ▾」，颜色随状态变（绿/黄/红/灰）
 * 展开后 8 行详情：code + 名称 + 状态 + 成分数/错误 + 失败行可重试
 */
function IndexStatusPopover({
  results,
  holdingsStatus,
  refreshing,
  onRetry,
  open,
  onToggle,
  onClose,
}: {
  results?: IndexRefreshItem[];
  holdingsStatus?: HoldingsStatus;
  refreshing: Record<string, boolean>;
  onRetry: (code: string) => void;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}) {
  const totalCount = CORE_DIVIDEND_INDEXES.length;

  // 单行数据合并：优先 indexResults（精确状态），其次 holdingsStatus（CSV 覆盖度），最后 unknown
  type RowState =
    | { kind: 'refreshed_success'; item: IndexRefreshItem }
    | { kind: 'refreshed_failed'; item: IndexRefreshItem }
    | { kind: 'in_holdings' }
    | { kind: 'missing_in_holdings' }
    | { kind: 'unknown' };

  function getRowState(code: string): RowState {
    const irItem = results?.find(r => r.code === code);
    if (irItem) {
      // 单指数刷成功判断：success（持仓刷成功）+ prefilter_resynced（prefilter 重算也成功）
      // 旧后端响应无 prefilter_resynced 字段时 ?? true 兜底，保持向后兼容
      const isFullSuccess =
        irItem.success && (irItem.prefilter_resynced ?? true);
      return isFullSuccess
        ? { kind: 'refreshed_success', item: irItem }
        : { kind: 'refreshed_failed', item: irItem };
    }
    if (holdingsStatus) {
      if (holdingsStatus.actual_index_codes.includes(code)) {
        return { kind: 'in_holdings' };
      }
      return { kind: 'missing_in_holdings' };
    }
    return { kind: 'unknown' };
  }

  // 触发按钮统计
  let successCount = 0;
  let failedCount = 0;
  CORE_DIVIDEND_INDEXES.forEach(({ code }) => {
    const s = getRowState(code);
    if (s.kind === 'refreshed_success' || s.kind === 'in_holdings') successCount++;
    else if (s.kind === 'refreshed_failed' || s.kind === 'missing_in_holdings') failedCount++;
  });
  const hasAnyData = successCount + failedCount > 0;
  const anyRefreshing = Object.values(refreshing).some(Boolean);

  // 触发按钮配色
  const btnClass = !hasAnyData
    ? 'bg-paper-tint text-gray-400 border border-rule hover:text-ink-strong'
    : successCount === totalCount
      ? 'bg-green-900/30 text-green-300 border border-green-700/50 hover:bg-green-900/40'
      : failedCount === totalCount
        ? 'bg-red-900/40 text-red-300 border border-red-700/50 hover:bg-red-900/50'
        : 'bg-amber-900/30 text-amber-300 border border-amber-700/50 hover:bg-amber-900/40';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        disabled={anyRefreshing}
        title="红利指数持仓刷新状态"
        className={`
          px-3 py-2 rounded font-medium transition-all flex items-center gap-1.5 text-sm whitespace-nowrap
          ${btnClass}
          ${anyRefreshing ? 'opacity-60 cursor-wait' : 'cursor-pointer'}
        `}
      >
        {anyRefreshing ? (
          <svg className="w-3 h-3 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        ) : successCount === totalCount && hasAnyData ? (
          <span className="text-green-400">✓</span>
        ) : failedCount > 0 && hasAnyData ? (
          <span className="text-amber-400">⚠</span>
        ) : null}
        <span>指数 {hasAnyData ? `${successCount}/${totalCount}` : `-${totalCount}`}</span>
        <svg
          className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 bg-paper-card border border-rule rounded-lg shadow-xl z-50">
          <div className="px-3 py-2 border-b border-rule flex justify-between items-center">
            <span className="font-medium text-ink text-sm">红利指数持仓状态</span>
            <button
              type="button"
              onClick={onClose}
              className="text-ink-muted hover:text-ink-strong text-xs"
              aria-label="关闭"
            >✕</button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {CORE_DIVIDEND_INDEXES.map(({ code, label }, idx) => {
              const state = getRowState(code);
              const isRefreshing = refreshing[code];
              return (
                <div
                  key={code}
                  className={`px-3 py-2 flex items-center gap-2 text-sm ${idx < CORE_DIVIDEND_INDEXES.length - 1 ? 'border-b border-rule/30' : ''}`}
                >
                  <span className="font-mono text-xs text-ink-muted w-16 shrink-0">{label}</span>
                  <span className="text-ink flex-1 truncate min-w-0">
                    {state.kind === 'refreshed_success' || state.kind === 'refreshed_failed'
                      ? (state.item.name || <span className="text-ink-muted">—</span>)
                      : <span className="text-ink-muted text-xs">（持仓 CSV）</span>}
                  </span>
                  {isRefreshing ? (
                    <span className="text-xs text-ink-muted animate-pulse shrink-0">刷新中…</span>
                  ) : state.kind === 'refreshed_success' ? (
                    <span className="text-xs text-green-400 shrink-0">✓ {state.item.constituents_count}只</span>
                  ) : state.kind === 'refreshed_failed' ? (
                    <>
                      <span
                        className="text-xs text-red-400 shrink-0 max-w-32 truncate"
                        title={
                          state.item.prefilter_resynced === false
                            ? `prefilter 同步失败：${state.item.prefilter_error || '详见后端日志'}`
                            : state.item.error || '失败'
                        }
                      >
                        ✗{' '}
                        {state.item.prefilter_resynced === false
                          ? 'prefilter 失败'
                          : state.item.error || '失败'}
                      </span>
                      <button
                        type="button"
                        onClick={() => onRetry(code)}
                        className="text-xs px-2 py-0.5 bg-red-900/40 text-red-300 hover:bg-red-900/60 rounded shrink-0"
                      >重试</button>
                    </>
                  ) : state.kind === 'in_holdings' ? (
                    <span className="text-xs text-green-400 shrink-0">✓ 持仓已有</span>
                  ) : state.kind === 'missing_in_holdings' ? (
                    <>
                      <span className="text-xs text-red-400 shrink-0">✗ 持仓缺失</span>
                      <button
                        type="button"
                        onClick={() => onRetry(code)}
                        className="text-xs px-2 py-0.5 bg-red-900/40 text-red-300 hover:bg-red-900/60 rounded shrink-0"
                      >重试</button>
                    </>
                  ) : (
                    <span className="text-xs text-ink-muted shrink-0">未刷新</span>
                  )}
                </div>
              );
            })}
          </div>
          {!hasAnyData && (
            <div className="px-3 py-2 border-t border-rule text-xs text-ink-muted">
              点击「更新股息率」触发刷新后查看状态
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * 把后端返回的 AlertStatusItem 转成 AlertSettingsModal 的 currentConfig 入参
 */
function buildCurrentConfig(item: AlertStatusItem | undefined): AlertConfigRequest | null {
  if (!item) return null;
  return {
    enabled: item.enabled,
    levels: item.levels ?? {
      heavy_position: null,
      add_position: null,
      reduce_position: null,
      full_exit: null,
    },
  };
}

export default function DividendPage() {
  return (
    <Suspense fallback={<div className="container mx-auto px-8 py-8 min-h-screen bg-paper" />}>
      <DividendPageContent />
    </Suspense>
  );
}

function DividendPageContent() {
  // 交易所筛选
  const [exchangeFilter, setExchangeFilter] = useState<string>('');
  // 股息率阈值输入
  const [minYieldInput, setMinYieldInput] = useState('3.5');

  // 股息率数据
  const { data, total, loading, error, refetch } = useDividendData();

  // 全量股票数（来自 /api/dividend/stats，未应用 min_yield 筛选）
  const [totalCollected, setTotalCollected] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    dividendApi.getStats().then((s) => {
      if (!cancelled) setTotalCollected(s.total_stocks);
    }).catch((err) => {
      // 接口失败时静默降级——头部文案显示「共 X 只」即可
      console.error('获取全量股票数失败:', err);
    });
    return () => { cancelled = true; };
  }, []);

  // 刷新计数，用于强制表格重新渲染
  const [refreshKey, setRefreshKey] = useState(0);

  // 输出报告下拉菜单开关
  const [reportOpen, setReportOpen] = useState(false);

  // 更新辅助数据下拉菜单开关
  const [auxOpen, setAuxOpen] = useState(false);
  const [auxForce, setAuxForce] = useState(false);
  // 每行独立的"强制"开关：key = 'sw_industry' | 'financial' | 'shareholder' | 'board'
  const [auxForceMap, setAuxForceMap] = useState<Record<string, boolean>>({});
  const auxMenuRef = useRef<HTMLDivElement>(null);

  // 红利指数状态 popover 开关
  const [indexPopoverOpen, setIndexPopoverOpen] = useState(false);
  const indexPopoverRef = useRef<HTMLDivElement>(null);

  // 辅助数据菜单 + 指数 popover：点击外部 / Esc 关闭
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (auxOpen && auxMenuRef.current && !auxMenuRef.current.contains(e.target as Node)) {
        setAuxOpen(false);
      }
      if (indexPopoverOpen && indexPopoverRef.current && !indexPopoverRef.current.contains(e.target as Node)) {
        setIndexPopoverOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAuxOpen(false);
        setIndexPopoverOpen(false);
      }
    };
    if (auxOpen || indexPopoverOpen) {
      document.addEventListener('mousedown', handleClick);
      document.addEventListener('keydown', handleKey);
    }
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [auxOpen, indexPopoverOpen]);

  // 下载报告（A4 一图版 / 手机竖版）
  const downloadReport = async (type: 'a4' | 'carousel') => {
    setReportOpen(false);
    const config = type === 'a4'
      ? { endpoint: '/api/dividend/report/one-pager', prefix: 'dividend_one_pager' }
      : { endpoint: '/api/dividend/report/carousel', prefix: 'dividend_carousel' };
    try {
      // 走前端 catch-all 代理（apps/dividend/src/app/api/dividend/report/.../route.ts）
      // 不再硬编码后端 URL，避免生产部署 404
      const response = await fetch(config.endpoint);
      if (!response.ok) throw new Error('生成报告失败');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${config.prefix}_${new Date().toISOString().slice(0, 10)}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('导出报告失败:', err);
      alert('导出报告失败，请稍后重试');
    }
  };

  // 股票代码列表
  const stockCodes = useMemo(() => data.map(s => s.code), [data]);

  // 技术指标数据
  const { technicalData } = useTechnicalData(stockCodes, refreshKey, parseFloat(minYieldInput) || 0);

  // 详情弹框
  const detailModal = useDetailModal();

  // 对比功能
  const compare = useCompare(MAX_COMPARE_SELECT);

  // 数据更新功能
  const { state: updateState, m120NeedsUpdate, m120MissingCodes, dividendNeedsUpdate, financialNeedsUpdate, financialMissingCodes, boardMissingCodes, auxStatuses, checkAuxStatus, updateDividend, updateM120, updateRealtimeInfo, updateFinancial, updateSwIndustry, updateShareholder, updateBoard, indexResults, indexRefreshing, refreshIndexHoldings, holdingsStatus } = useDataUpdate();

  // 收藏（watchlist）
  const watchlist = useWatchlist();

  // 挡位监控状态
  const alertsStatus = useAlertsStatus();
  const [alertStock, setAlertStock] = useState<DividendStock | null>(null);
  const [alertOpen, setAlertOpen] = useState(false);
  const [schedulerOpen, setSchedulerOpen] = useState(false);

  const handleOpenAlertSettings = useCallback((code: string) => {
    const s = data.find(x => x.code === code);
    if (s) {
      setAlertStock(s);
      setAlertOpen(true);
    } else {
      alert(`未找到股票 ${code}，请刷新页面后重试`);
    }
  }, [data]);

  // URL query 同步 tab（?tab=watchlist / ?tab=alerts）
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab');
  const activeTab: TabKey =
    tabParam === 'watchlist' ? 'watchlist' :
    tabParam === 'alerts' ? 'alerts' : 'all';
  const handleTabChange = useCallback((tab: TabKey) => {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === 'all') params.delete('tab');
    else params.set('tab', tab);
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : '?', { scroll: false });
  }, [router, searchParams]);

  // 抽屉引用
  const drawerRef = useRef<HTMLDivElement>(null);

  // 合并股票数据和技术指标
  const stocksWithTechnical: DividendStockWithTechnical[] = useMemo(() => {
    return data.map(stock => ({
      ...stock,
      technical: technicalData.get(stock.code) || undefined,
    }));
  }, [data, technicalData]);

  // 按 tab 过滤显示数据
  const displayData = useMemo(() => {
    if (activeTab === 'watchlist') {
      return stocksWithTechnical.filter(s => watchlist.has(s.code));
    }
    return stocksWithTechnical;
  }, [stocksWithTechnical, activeTab, watchlist]);

  // 挡位监控 Tab：filter 已设 alerts 的收藏股票
  const alertStocks = useMemo(() => {
    const items = alertsStatus.status?.items ?? [];
    return items
      .filter(it => it.levels && Object.values(it.levels).some(lv => lv && lv.price))
      .map(it => {
        const stock = stocksWithTechnical.find(s => s.code === it.code);
        if (!stock) return null;
        return { stock, levels: it.levels as AlertLevels };
      })
      .filter((s): s is { stock: DividendStockWithTechnical; levels: AlertLevels } => s !== null);
  }, [alertsStatus.status, stocksWithTechnical]);

  // 处理弹框
  const handleOpenModal = useCallback((type: 'quarterly' | 'sector' | 'yearly' | 'volatility', stock: DividendStock) => {
    detailModal.open(type, stock);
  }, [detailModal]);

  // 处理对比
  const handleToggleCompare = useCallback((stock: DividendStock) => {
    compare.toggleStock(stock);
  }, [compare]);

  // 骨架屏
  if (loading && data.length === 0) {
    return (
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-paper">
        <div className="mb-6">
          <div className="h-8 bg-paper-card rounded w-48 mb-2 animate-pulse"></div>
          <div className="h-5 bg-paper-card rounded w-32 animate-pulse"></div>
        </div>
        <div className="bg-paper-card rounded-lg h-[500px] animate-pulse"></div>
      </div>
    );
  }

  // 空数据提示
  if (!loading && data.length === 0 && !error) {
    return (
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-paper">
        <div className="mb-6">
          <div className="flex justify-between items-start">
            <div>
              <Link href="/" className="text-ink-muted hover:text-ink-strong transition-colors">
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4 text-ink">股息率</h1>
            </div>
            <button
              onClick={updateDividend}
              disabled={updateState.dividend === 'loading'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap
                ${updateState.dividend === 'loading'
                  ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
            >
              {updateState.dividend === 'loading' ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  刷新中...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  更新股息率
                </>
              )}
            </button>
          </div>
        </div>
        <div className="bg-paper-card rounded-lg p-8 text-center">
          <div className="text-6xl mb-4">📊</div>
          <h2 className="text-xl font-semibold text-ink mb-2">本月股息率数据未计算</h2>
          <p className="text-ink-muted mb-6">请点击上方「更新股息率」按钮获取数据</p>
          {updateState.message && (
            <div className="bg-blue-900/50 border border-blue-700 text-blue-200 px-4 py-3 rounded inline-block">
              {updateState.message}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-paper">
      {/* 头部导航 */}
      <div className="mb-6">
        <div className="flex justify-between items-start">
          <div>
            <Link href="/" className="text-ink-muted hover:text-ink-strong transition-colors">
              ← 返回首页
            </Link>
            <h1 className="text-4xl font-bold mt-4 text-ink">股息率</h1>
            <p className="text-ink-muted mt-1">
              {totalCollected !== null
                ? `共收集 ${totalCollected} 只股票，其中 ${total} 只 3年股息率 ≥ ${minYieldInput}%`
                : `共 ${total} 只股票 | 3年股息率 ≥ ${minYieldInput}%`}
            </p>
            {/* 筛选条件 */}
            <div className="mt-2 flex items-center gap-3">
              <label className="text-sm text-ink-muted">交易所:</label>
              <select
                value={exchangeFilter}
                onChange={(e) => setExchangeFilter(e.target.value)}
                className="bg-paper-card text-ink border border-rule-strong rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
              >
                <option value="">全部</option>
                <option value="沪市主板">沪市主板</option>
                <option value="深市主板">深市主板</option>
              </select>
              <label className="text-sm text-ink-muted ml-2">股息率≥:</label>
              <input
                type="number"
                value={minYieldInput}
                onChange={(e) => setMinYieldInput(e.target.value)}
                className="bg-paper-card text-ink border border-rule-strong rounded px-3 py-1.5 text-sm w-20 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
                placeholder="3"
                min="0"
                step="0.1"
              />
              <span className="text-sm text-ink-muted">%</span>
              <button
                onClick={() => {
                  const minYield = minYieldInput === '' ? 3.5 : (parseFloat(minYieldInput) || 0);
                  refetch({
                    min_yield: minYield,
                    exchange: exchangeFilter || undefined,
                  });
                  setRefreshKey(k => k + 1);
                }}
                disabled={loading}
                className={`
                  px-4 py-1.5 rounded font-medium transition-all flex items-center gap-2 text-sm
                  ${loading
                    ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                    : 'bg-indigo-600 text-white hover:bg-indigo-500'
                  }
                `}
              >
                <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                查询
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div ref={indexPopoverRef}>
              <IndexStatusPopover
                results={indexResults}
                holdingsStatus={holdingsStatus}
                refreshing={indexRefreshing}
                onRetry={refreshIndexHoldings}
                open={indexPopoverOpen}
                onToggle={() => setIndexPopoverOpen(!indexPopoverOpen)}
                onClose={() => setIndexPopoverOpen(false)}
              />
            </div>

            <button
              onClick={updateDividend}
              disabled={!dividendNeedsUpdate || updateState.dividend === 'loading'}
              title={dividendNeedsUpdate ? '本月数据待更新' : '本月数据已更新'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap
                ${!dividendNeedsUpdate || updateState.dividend === 'loading'
                  ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
            >
              {updateState.dividend === 'loading' ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  刷新中...
                </>
              ) : updateState.dividend === 'success' && updateState.dividend_failed_count !== undefined ? (
                updateState.dividend_failed_count > 0 ? (
                  <>
                    <span className="text-amber-400">⚠️</span>
                    完成{updateState.dividend_completed_count}条，失败{updateState.dividend_failed_count}条
                  </>
                ) : (
                  <>
                    <span className="text-green-400">✅</span>
                    已是最新
                  </>
                )
              ) : dividendNeedsUpdate && updateState.dividend_target_count ? (
                <>
                  <span className="text-amber-400">📥</span>
                  待完成（{updateState.dividend_target_count - (updateState.dividend_completed_count || 0)}/{updateState.dividend_target_count}）
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  股息率
                </>
              )}
            </button>

            <div ref={auxMenuRef} className="relative">
              {(() => {
                const auxPendingCount =
                  (auxStatuses.sw_industry?.needs_update ? 1 : 0) +
                  (auxStatuses.financial?.needs_update ? 1 : 0) +
                  (auxStatuses.shareholder?.needs_update ? 1 : 0) +
                  (auxStatuses.board?.needs_update ? 1 : 0);
                const auxAnyLoading =
                  updateState.sw_industry === 'loading' ||
                  updateState.financial === 'loading' ||
                  updateState.shareholder === 'loading' ||
                  updateState.board === 'loading';
                return (
                  <>
                    <button
                      onClick={() => setAuxOpen(!auxOpen)}
                      disabled={auxAnyLoading}
                      className={`
                        px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap
                        ${auxAnyLoading
                          ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                          : auxPendingCount > 0
                            ? 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-md shadow-indigo-500/20'
                            : 'bg-paper-tint text-gray-400 border border-rule hover:text-ink-strong'
                        }
                      `}
                    >
                      {auxAnyLoading ? (
                        <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      ) : auxPendingCount > 0 ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      辅助数据
                      {auxPendingCount > 0 && (
                        <span className="bg-white/25 text-white text-[11px] font-mono font-semibold rounded-full px-1.5 min-w-[18px] h-[18px] inline-flex items-center justify-center -ml-1">
                          {auxPendingCount}
                        </span>
                      )}
                      <svg className={`w-3 h-3 transition-transform ${auxOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {auxOpen && (
                      <div className="absolute right-0 mt-1 bg-paper-card border border-rule rounded-lg shadow-lg z-50 w-[340px] overflow-hidden">
                        {(() => {
                          const auxItems: Array<{
                            key: 'sw_industry' | 'financial' | 'shareholder' | 'board';
                            label: string;
                            sub: string;
                            status: typeof auxStatuses.sw_industry;
                            updateFn: (force: boolean) => Promise<unknown>;
                            loadingKey: 'sw_industry' | 'financial' | 'shareholder' | 'board';
                          }> = [
                            { key: 'sw_industry', label: '申万行业', sub: '申万一级/二级/三级', status: auxStatuses.sw_industry, updateFn: updateSwIndustry, loadingKey: 'sw_industry' },
                            { key: 'financial', label: '财务指标', sub: '财报基础数据', status: auxStatuses.financial, updateFn: (force) => updateFinancial(financialMissingCodes.length > 0 ? financialMissingCodes : undefined, force), loadingKey: 'financial' },
                            { key: 'shareholder', label: '股东户数', sub: '披露日统计', status: auxStatuses.shareholder, updateFn: updateShareholder, loadingKey: 'shareholder' },
                            { key: 'board', label: '个股板块', sub: 'emweb 板块归属', status: auxStatuses.board, updateFn: (force) => updateBoard(boardMissingCodes.length > 0 ? boardMissingCodes : undefined, force), loadingKey: 'board' },
                          ];
                          return (
                            <>
                              {auxPendingCount > 0 && !auxAnyLoading && (
                                <div className="p-2.5 bg-gradient-to-b from-indigo-500/10 to-transparent border-b border-rule">
                                  <button
                                    onClick={async () => {
                                      const toUpdate = auxItems.filter(i => i.status?.needs_update);
                                      await Promise.all(
                                        toUpdate.map(i => i.updateFn(auxForceMap[i.key] ?? false))
                                      );
                                    }}
                                    className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                    </svg>
                                    全部更新
                                    <span className="bg-white/25 text-white text-[11px] font-mono font-semibold rounded-full px-1.5 min-w-[18px] h-[16px] inline-flex items-center justify-center">
                                      {auxPendingCount}
                                    </span>
                                    项
                                  </button>
                                </div>
                              )}
                              <div>
                                {auxItems.map(item => {
                                  const isLoading = updateState[item.loadingKey] === 'loading';
                                  const daysAgo = item.status?.days_since_update != null ? item.status.days_since_update : null;
                                  const isCurrent = !isLoading && !item.status?.needs_update;
                                  const rowForce = auxForceMap[item.key] ?? false;
                                  return (
                                    <div
                                      key={item.key}
                                      className={`
                                        relative flex items-center gap-3 px-3.5 pl-[13px] py-2.5
                                        border-b border-rule last:border-b-0
                                        border-l-[3px] transition-colors
                                        ${isLoading ? 'border-l-info bg-paper-card' :
                                          isCurrent ? 'border-l-up hover:bg-paper-tint' : 'border-l-amber-400 hover:bg-paper-tint'}
                                      `}
                                    >
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-0.5">
                                          <span className="font-medium text-ink text-[13px]">{item.label}</span>
                                          {isLoading ? (
                                            <span className="text-[11px] font-mono text-blue-400 inline-flex items-center gap-1">
                                              <span className="w-2.5 h-2.5 border-[1.5px] border-blue-400 border-t-transparent rounded-full animate-spin" />
                                              拉取中
                                            </span>
                                          ) : (
                                            <span className={`text-[11px] font-mono ${isCurrent ? 'text-emerald-400' : 'text-amber-400'}`}>
                                              {daysAgo != null ? `${daysAgo} 天前` : '从未更新'}
                                            </span>
                                          )}
                                        </div>
                                        <div className="text-[11px] text-ink-muted">
                                          {item.sub}
                                          {item.status?.quarter ? ` · ${item.status.quarter}` : ''}
                                        </div>
                                        {isLoading && (
                                          <div className="absolute bottom-0 left-0 right-0 h-[2px] overflow-hidden">
                                            <div
                                              className="h-full bg-gradient-to-r from-blue-400 to-indigo-500"
                                              style={{
                                                width: '40%',
                                                animation: 'indeterminate 1.5s ease-in-out infinite',
                                              }}
                                            />
                                          </div>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-1.5 flex-shrink-0">
                                        <label
                                          className={`
                                            flex items-center gap-1 text-[10px] uppercase tracking-wider font-mono font-medium
                                            px-1.5 py-0.5 rounded border cursor-pointer select-none transition-colors
                                            ${rowForce
                                              ? 'text-amber-400 bg-amber-400/10 border-amber-400/30'
                                              : 'text-gray-500 border-transparent hover:text-gray-400 hover:bg-paper-deep'
                                            }
                                          `}
                                          title="强制覆盖（绕过 90 天节流）"
                                        >
                                          <input
                                            type="checkbox"
                                            checked={rowForce}
                                            onChange={e => setAuxForceMap(prev => ({ ...prev, [item.key]: e.target.checked }))}
                                            className="hidden"
                                          />
                                          <span className={`w-2.5 h-2.5 border border-current rounded-sm flex items-center justify-center ${rowForce ? 'bg-amber-400' : ''}`}>
                                            {rowForce && <span className="text-[8px] text-black font-bold leading-none">✓</span>}
                                          </span>
                                          强制
                                        </label>
                                        <button
                                          disabled={isLoading}
                                          onClick={() => item.updateFn(rowForce)}
                                          className={`
                                            text-[11px] font-medium px-2.5 py-1 rounded border transition-colors
                                            ${isLoading
                                              ? 'border-rule text-ink-soft cursor-not-allowed'
                                              : 'border-rule-strong text-ink hover:bg-accent hover:border-accent hover:text-white'
                                            }
                                          `}
                                        >
                                          {isLoading ? '更新中' : '更新'}
                                        </button>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>

            <button
              onClick={() => {
                // 优先传 missing_codes（增量补缺），没有缺失才传全集
                const codesToUpdate = m120MissingCodes.length > 0 ? m120MissingCodes : stockCodes;
                updateM120(codesToUpdate);
                setRefreshKey(k => k + 1);
              }}
              disabled={!m120NeedsUpdate || updateState.m120 === 'loading'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap
                ${!m120NeedsUpdate || updateState.m120 === 'loading'
                  ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
              title={m120NeedsUpdate ? "更新 M120 均线（有缺失数据）" : "更新 M120 均线（已是最新）"}
            >
              <svg
                className={`w-4 h-4 ${updateState.m120 === 'loading' ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              M120
            </button>

            <button
              onClick={() => {
                updateRealtimeInfo(stockCodes);
                setRefreshKey(k => k + 1);
              }}
              disabled={updateState.realtime === 'loading'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap
                ${updateState.realtime === 'loading'
                  ? 'bg-paper-deep text-ink-muted cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
              title="更新实时价格（每日更新一次）"
            >
              <svg
                className={`w-4 h-4 ${updateState.realtime === 'loading' ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              实时价
            </button>

            {/* 定时任务管理：slate-600 中性色，避开主操作色（indigo）+ 次操作色（green/blue） */}
            <button
              onClick={() => setSchedulerOpen(true)}
              className="px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap bg-slate-600 text-white hover:bg-slate-500"
              title="定时任务管理"
              aria-label="定时任务"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              定时任务
            </button>
          </div>

          {/* 第二行：导出按钮，靠右 */}
          <div className="flex justify-end items-center gap-2 mt-2">
            <button
              onClick={() => {
                const headers = [
                  '股票代码', '股票名称', '交易所', '申万一级行业', '申万二级行业', '申万三级行业',
                  '3年平均股息率(%)', '实时股息率(%)', '实时股息率TTM(%)',
                  'M120', '实时价格', '收盘价/M120',
                  '股东户数(万)', '股东人数增幅(%)', '人均持股',
                  '扣非净利润同比(%)', '3年复合增长率(%)',
                  '最近年报年度', 'EPS(元)', '分红比例(%)'
                ];

                const rows = stocksWithTechnical.map(stock => {
                  const tech = stock.technical;
                  const yield_3y = stock.avg_yield_3y ? stock.avg_yield_3y.toFixed(2) : '';
                  const realtime_yield = (stock.dividend_2025 && tech?.realtime)
                    ? (stock.dividend_2025 / tech.realtime * 100).toFixed(2) : '';
                  const yield_ttm = tech?.yield_ttm ? tech.yield_ttm.toFixed(2) : '';
                  const m120 = tech?.m120 ? tech.m120.toFixed(2) : '';
                  const realtime = tech?.realtime ? tech.realtime.toFixed(2) : '';
                  const deviation = tech?.realtimeDeviation ? tech.realtimeDeviation.toFixed(2) : '';
                  const shareholder_count = stock.shareholder_count
                    ? (stock.shareholder_count / 10000).toFixed(1) : '';
                  const shareholder_change = stock.shareholder_change_pct
                    ? stock.shareholder_change_pct.toFixed(2) : '';
                  const per_share = stock.per_share_holding
                    ? stock.per_share_holding.toFixed(0) : '';
                  const yoy = stock.net_profit_ex_non_recurring_yoy != null
                    ? stock.net_profit_ex_non_recurring_yoy.toFixed(2) : '无法计算';
                  const cagr = stock.net_profit_cagr_3y != null
                    ? stock.net_profit_cagr_3y.toFixed(2) : '无法计算';
                  const eps_year_csv = stock.eps_year ?? '';
                  const eps_csv = stock.eps != null ? stock.eps.toFixed(4) : '';
                  const payout_csv = stock.payout_ratio != null ? stock.payout_ratio.toFixed(2) : '';

                  return [
                    stock.code, stock.name, stock.exchange,
                    stock.sw_level1 || '', stock.sw_level2 || '', stock.sw_level3 || '',
                    yield_3y, realtime_yield, yield_ttm,
                    m120, realtime, deviation,
                    shareholder_count, shareholder_change, per_share,
                    yoy, cagr,
                    eps_year_csv, eps_csv, payout_csv
                  ].join(',');
                });

                const csv = [headers.join(','), ...rows].join('\n');
                const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `dividend_export_${new Date().toISOString().slice(0, 10)}.csv`;
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap bg-green-600 text-white hover:bg-green-500"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              CSV
            </button>

            <div
              className="relative"
              onMouseLeave={() => setReportOpen(false)}
            >
              <button
                onClick={() => setReportOpen(!reportOpen)}
                className="px-4 py-2 rounded font-medium transition-all flex items-center gap-2 whitespace-nowrap bg-blue-600 text-white hover:bg-blue-500"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                报告
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {reportOpen && (
                <div className="absolute right-0 mt-1 bg-paper-card border border-rule rounded-lg shadow-lg z-50 min-w-[200px] overflow-hidden">
                  <button
                    onClick={() => downloadReport('a4')}
                    className="block w-full text-left px-4 py-2 text-sm text-ink hover:bg-paper-tint first:rounded-t"
                  >
                    <div className="font-medium">A4 一图版（横版）</div>
                    <div className="text-xs text-ink-muted mt-0.5">适合电脑端分享/打印</div>
                  </button>
                  <button
                    onClick={() => downloadReport('carousel')}
                    className="block w-full text-left px-4 py-2 text-sm text-ink hover:bg-paper-tint last:rounded-b border-t border-rule"
                  >
                    <div className="font-medium">手机竖版（轮播）</div>
                    <div className="text-xs text-ink-muted mt-0.5">1080×1920 · 支持⬇下载原图</div>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 更新状态提示 */}
      {updateState.message && (
        <div className="mb-4 bg-blue-900/50 border border-blue-700 text-blue-200 px-4 py-3 rounded">
          {updateState.message}
        </div>
      )}

      {/* Tab 切换 */}
      <div className="flex border-b border-gray-700 mb-4">
        <button
          onClick={() => handleTabChange('all')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'all'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          全部
          <span className="ml-2 text-xs bg-gray-700 px-1.5 py-0.5 rounded">{stocksWithTechnical.length}</span>
        </button>
        <button
          onClick={() => handleTabChange('watchlist')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === 'watchlist'
              ? 'border-yellow-500 text-yellow-400'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <StarIconOutline className="w-4 h-4" />
          收藏
          <span className="ml-1 text-xs bg-gray-700 px-1.5 py-0.5 rounded">{watchlist.total}</span>
        </button>
        <button
          onClick={() => handleTabChange('alerts')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === 'alerts'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 17l6-6 4 4 8-8M14 7h7v7" />
          </svg>
          挡位监控
          <span className="ml-1 text-xs bg-gray-700 px-1.5 py-0.5 rounded">{alertStocks.length}</span>
        </button>
      </div>

      {/* 收藏 tab 空状态 */}
      {activeTab === 'watchlist' && displayData.length === 0 && !loading && (
        <div className="bg-paper-card rounded-lg p-12 text-center">
          <StarIconOutline className="w-12 h-12 mx-auto mb-3 text-gray-500" />
          <p className="text-gray-400 mb-4">
            {watchlist.total === 0 ? '还没有收藏的股票' : '本月筛选范围内暂无收藏的股票'}
          </p>
          <button
            onClick={() => handleTabChange('all')}
            className="text-blue-400 hover:underline text-sm"
          >
            去全部 tab 添加 →
          </button>
        </div>
      )}

      {/* 表格 - 使用 refreshKey 作为 key 强制刷新；watchlist tab 用 displayData，其他用 stocksWithTechnical */}
      {activeTab === 'alerts' ? (
        <div className="space-y-2">
          {alertStocks.length === 0 ? (
            <div className="bg-paper-card rounded-lg p-12 text-center">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 17l6-6 4 4 8-8M14 7h7v7" />
              </svg>
              <h2 className="text-xl font-semibold text-ink mb-2">暂无设置挡位的收藏股票</h2>
              <p className="text-ink-muted mb-4">去「收藏」或筛一下其他股票后点行设置挡位</p>
              <button
                onClick={() => handleTabChange('all')}
                className="text-blue-400 hover:underline text-sm"
              >
                去全部 tab 浏览 →
              </button>
            </div>
          ) : (
            alertStocks.map(({ stock, levels }) => {
              const tech = technicalData.get(stock.code);
              const currentPrice = tech?.realtime ?? tech?.close ?? null;
              if (currentPrice === null || currentPrice === undefined) return null;
              return (
                <AlertLevelBar
                  key={stock.code}
                  code={stock.code}
                  name={stock.name}
                  levels={levels}
                  currentPrice={currentPrice}
                  currentPE={tech?.pe ?? null}
                  currentPB={tech?.pb ?? null}
                  dividend2025={stock.dividend_2025 ?? null}
                  yieldTtm={tech?.yield_ttm ?? null}
                  onClick={() => handleOpenAlertSettings(stock.code)}
                />
              );
            })
          )}
        </div>
      ) : (
        !(activeTab === 'watchlist' && displayData.length === 0) && (
          <DividendTable
            key={refreshKey}
            data={displayData}
            technicalData={technicalData}
            onOpenModal={handleOpenModal}
            selectedStockCodes={compare.selectedStocks.map(s => s.code)}
            maxSelect={MAX_COMPARE_SELECT}
            onToggleCompare={handleToggleCompare}
            watchlist={watchlist.codes}
            onToggleWatchlist={watchlist.toggle}
            alertStatusItems={alertsStatus.alertMap}
            onOpenAlertSettings={handleOpenAlertSettings}
          />
        )
      )}

      {/* 详情弹框 */}
      <DetailModal
        isOpen={detailModal.isOpen}
        onClose={detailModal.close}
        type={detailModal.modalType}
        stock={detailModal.stock}
      />

      {/* 挡位设置弹框 */}
      <AlertSettingsModal
        isOpen={alertOpen}
        onClose={() => setAlertOpen(false)}
        stock={alertStock}
        technical={alertStock ? technicalData.get(alertStock.code) || null : null}
        currentConfig={alertStock ? buildCurrentConfig(alertsStatus.alertMap.get(alertStock.code)) : null}
        currentUpdatedAt={alertStock ? alertsStatus.alertMap.get(alertStock.code)?.updated_at ?? null : null}
        onSubmit={async (code, body) => {
          await alertsStatus.setAlerts(code, body);
        }}
        onClear={async (code) => {
          await alertsStatus.clearAlerts(code);
        }}
      />

      {/* 定时任务管理弹框 */}
      <SchedulerSettingsModal
        isOpen={schedulerOpen}
        onClose={() => setSchedulerOpen(false)}
      />

      {/* 对比浮动栏 */}
      <CompareFloatingBar
        selectedCount={compare.selectedStocks.length}
        selectedStocks={compare.selectedStocks}
        maxSelect={MAX_COMPARE_SELECT}
        onOpenCompare={compare.openDrawer}
        onClear={compare.clearSelection}
        isVisible={compare.selectedStocks.length > 0}
      />

      {/* 对比抽屉 */}
      <CompareDrawer
        isOpen={compare.isDrawerOpen}
        onClose={compare.closeDrawer}
        stocks={compare.selectedStocks.map(stock => ({
          ...stock,
          technical: technicalData.get(stock.code) || undefined,
        }))}
        onRemove={compare.removeStock}
        drawerRef={drawerRef}
      />
    </div>
  );
}
