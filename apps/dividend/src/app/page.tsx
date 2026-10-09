/**
 * 股息率页面
 * 展示高股息率股票列表及技术指标
 */
'use client';

import { Suspense, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { StarIcon as StarIconOutline } from '@heroicons/react/24/outline';
import { ScreeningTab } from '@/components/ScreeningTab';
import { DividendTable } from '@/components/DividendTable';
import { DetailModal } from '@/components/DetailModal';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { CompareDrawer } from '@/components/CompareDrawer';
import { AlertSettingsModal } from '@/components/AlertSettingsModal';
import { AlertLevelBar } from '@/components/AlertLevelBar';
import { SchedulerSettingsModal } from '@/components/SchedulerSettingsModal';
import { DataUpdateDrawer } from '@/components/DataUpdateDrawer';
import { useDividendData, useTechnicalData, useDetailModal, useCompare, useDataUpdate } from '@/lib/hooks';
import { useWatchlist } from '@/lib/hooks/useWatchlist';
import { useAlertsStatus } from '@/lib/hooks/useAlertsStatus';
import { useRealtimePrices } from '@/lib/hooks/useRealtimePrices';
import { dividendApi } from '@/lib/api';
import type { DividendStock, DividendStockWithTechnical, AlertConfigRequest, AlertStatusItem, AlertLevels, IndexRefreshItem, HoldingsStatus } from '@/lib/types';

const MAX_COMPARE_SELECT = 5;
type TabKey = 'all' | 'alerts' | 'screening';

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
 * 数据更新抽屉里的任务行：左侧名称 + 状态副文案，右侧「更新」动作按钮。
 * tone 决定左状态色条；传 onToggle 时整行可点（展开子列表）。
 */
function UpdateTaskRow({
  label,
  sub,
  tone,
  actionLabel = '更新',
  onAction,
  actionDisabled = false,
  onToggle,
  expanded = false,
  children,
}: {
  label: string;
  sub: React.ReactNode;
  tone: 'idle' | 'pending' | 'loading' | 'ok';
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  onToggle?: () => void;
  expanded?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <div
        onClick={onToggle}
        className={`
          flex items-center gap-3 px-3 pl-[13px] py-2.5 border-l-[3px] transition-colors
          ${tone === 'loading'
            ? 'border-l-info'
            : tone === 'pending'
              ? 'border-l-amber-400'
              : tone === 'ok'
                ? 'border-l-up'
                : 'border-l-rule'}
          ${onToggle ? 'cursor-pointer hover:bg-paper-tint' : ''}
        `}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-medium text-ink">{label}</span>
            {onToggle && (
              <svg className={`w-3 h-3 text-ink-muted transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            )}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-muted">{sub}</div>
        </div>
        {onAction && (
          <button
            type="button"
            disabled={actionDisabled}
            onClick={(e) => { e.stopPropagation(); onAction(); }}
            className={`
              flex-shrink-0 text-[11px] font-medium px-2.5 py-1 rounded border transition-colors
              ${actionDisabled
                ? 'border-rule text-ink-soft cursor-not-allowed'
                : 'border-rule-strong text-ink hover:bg-accent hover:border-accent hover:text-white'}
            `}
          >
            {actionLabel}
          </button>
        )}
      </div>
      {expanded && children}
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
  const [exportOpen, setExportOpen] = useState(false);

  // 更新辅助数据下拉菜单开关
  const [auxOpen, setAuxOpen] = useState(false);
  const [auxForce, setAuxForce] = useState(false);
  // 每行独立的"强制"开关：key = 'sw_industry' | 'financial' | 'shareholder' | 'board'
  const [auxForceMap, setAuxForceMap] = useState<Record<string, boolean>>({});

  // 红利指数状态 popover 开关
  const [indexPopoverOpen, setIndexPopoverOpen] = useState(false);
  const indexPopoverRef = useRef<HTMLDivElement>(null);

  // 指数 popover：点击外部 / Esc 关闭；辅助数据为内嵌展开，Esc 关闭即可
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
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
    setExportOpen(false);
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

  // 导出 CSV 表格（当前筛选结果全字段）
  const downloadCsv = () => {
    setExportOpen(false);
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
    const blob = new Blob([String.fromCharCode(0xfeff) + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dividend_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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

  const [favoriteStocks, setFavoriteStocks] = useState<DividendStock[]>([]);
  const [favoriteLoadError, setFavoriteLoadError] = useState('');
  useEffect(() => {
    let cancelled = false;
    if (watchlist.codes.size === 0) { setFavoriteStocks([]); return; }
    dividendApi.getStocks({ min_yield: 0 }).then(response => {
      if (!cancelled) { setFavoriteStocks(response.items); setFavoriteLoadError(''); }
    }).catch(err => { if (!cancelled) setFavoriteLoadError(err instanceof Error ? err.message : '收藏资料加载失败'); });
    return () => { cancelled = true; };
  }, [watchlist.codes, refreshKey]);
  const independentFavorites: DividendStockWithTechnical[] = useMemo(() => [...watchlist.codes].map(code => {
    const stock = favoriteStocks.find(item => item.code === code) || data.find(item => item.code === code)
      || { code, name: '资料待补', exchange: '' };
    return { ...stock, technical: technicalData.get(code) };
  }), [watchlist.codes, favoriteStocks, data, technicalData]);

  // 挡位监控状态
  const alertsStatus = useAlertsStatus();
  const [alertStock, setAlertStock] = useState<DividendStock | null>(null);
  const [alertOpen, setAlertOpen] = useState(false);
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [dataUpdateOpen, setDataUpdateOpen] = useState(false);

  // 数据更新抽屉：辅助数据子项与汇总状态
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
  const auxPendingCount = auxItems.filter(i => i.status?.needs_update).length;
  const auxAnyLoading = auxItems.some(i => updateState[i.loadingKey] === 'loading');
  const updateAllAux = async () => {
    const toUpdate = auxItems.filter(i => i.status?.needs_update);
    await Promise.all(toUpdate.map(i => i.updateFn(auxForceMap[i.key] ?? false)));
  };

  const handleOpenAlertSettings = useCallback((code: string) => {
    const s = independentFavorites.find(x => x.code === code) || data.find(x => x.code === code);
    if (s) {
      setAlertStock(s);
      setAlertOpen(true);
    } else {
      alert(`未找到股票 ${code}，请刷新页面后重试`);
    }
  }, [data, independentFavorites]);

  // URL query 同步 tab（?tab=alerts）+ 收藏过滤（?fav=1）
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab');
  const activeTab: TabKey = tabParam === 'alerts' ? 'alerts' : tabParam === 'screening' ? 'screening' : 'all';
  // 兼容旧 ?tab=watchlist 书签 → 等价于 all + 只看收藏
  const favOnly = searchParams.get('fav') === '1' || tabParam === 'watchlist';
  const handleTabChange = useCallback((tab: TabKey) => {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === 'all') params.delete('tab');
    else params.set('tab', tab);
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : '?', { scroll: false });
  }, [router, searchParams]);
  const handleToggleFav = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (favOnly) { params.delete('fav'); if (params.get('tab') === 'watchlist') params.delete('tab'); }
    else params.set('fav', '1');
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : '?', { scroll: false });
  }, [router, searchParams, favOnly]);

  // 抽屉引用
  const drawerRef = useRef<HTMLDivElement>(null);

  // 合并股票数据和技术指标
  const stocksWithTechnical: DividendStockWithTechnical[] = useMemo(() => {
    return data.map(stock => ({
      ...stock,
      technical: technicalData.get(stock.code) || undefined,
    }));
  }, [data, technicalData]);

  // 按 tab + 收藏过滤显示数据（"只看收藏"仅在 all tab 生效）
  const displayData = useMemo(() => {
    if (activeTab === 'all' && favOnly) {
      return independentFavorites;
    }
    return stocksWithTechnical;
  }, [stocksWithTechnical, activeTab, favOnly, independentFavorites]);

  // 挡位监控 Tab：filter 已设 alerts 的收藏股票
  const alertStocks = useMemo(() => {
    const items = alertsStatus.status?.items ?? [];
    return items
      .filter(it => it.levels && Object.values(it.levels).some(lv => lv && lv.price))
      .map(it => {
        const stock = independentFavorites.find(s => s.code === it.code) || stocksWithTechnical.find(s => s.code === it.code);
        if (!stock) return null;
        return { stock, levels: it.levels as AlertLevels };
      })
      .filter((s): s is { stock: DividendStockWithTechnical; levels: AlertLevels } => s !== null);
  }, [alertsStatus.status, stocksWithTechnical, independentFavorites]);

  // 挡位监控现价（独立于 M120：M120 缺失时仍能取现价，避免挡位 bar 空窗）
  const alertCodes = useMemo(() => alertStocks.map(s => s.stock.code), [alertStocks]);
  const { priceMap: alertPriceMap, lastUpdated: alertPriceUpdatedAt } = useRealtimePrices(alertCodes);

  // 处理弹框
  const handleOpenModal = useCallback((type: 'quarterly' | 'sector' | 'yearly' | 'volatility', stock: DividendStock) => {
    detailModal.open(type, stock);
  }, [detailModal]);

  // 处理对比
  const handleToggleCompare = useCallback((stock: DividendStock) => {
    compare.toggleStock(stock);
  }, [compare]);

  // 骨架屏
  if (loading && data.length === 0 && activeTab === 'all' && !favOnly) {
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


  return (
    <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-paper">
      {/* 头部导航 */}
      <div className="mb-6">
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-start gap-2">
          <div>
            <Link href="/" className="text-ink-muted hover:text-ink-strong transition-colors">
              ← 返回首页
            </Link>
            <h1 className="text-4xl font-bold mt-4 text-ink">股息率</h1>
            <p className="text-ink-muted mt-1">
              {activeTab === 'screening' ? '按分红与经营质量筛选，收藏后持续关注' : totalCollected !== null
                ? `共收集 ${totalCollected} 只股票，其中 ${total} 只 3年股息率 ≥ ${minYieldInput}%`
                : `共 ${total} 只股票 | 3年股息率 ≥ ${minYieldInput}%`}
            </p>
            {/* 筛选条件 */}
            {activeTab !== 'screening' && <div className="mt-2 flex items-center gap-3">
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
            </div>}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDataUpdateOpen(true)}
              className="flex items-center gap-2 rounded border border-rule-strong bg-paper-card px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              数据更新
            </button>
            <DataUpdateDrawer
              isOpen={dataUpdateOpen}
              onClose={() => setDataUpdateOpen(false)}
              onOpenScheduler={() => setSchedulerOpen(true)}
            >
            <div className="space-y-4">
            <p className="pt-1 text-xs font-semibold tracking-wide text-ink-muted">更新任务</p>
            <div className="rounded-lg border border-rule bg-paper-card divide-y divide-rule">
            <div className="flex items-center gap-3 px-3 py-2.5">
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium text-ink">红利指数持仓</div>
                <div className="mt-0.5 text-[11px] text-ink-muted">指数成分股持仓 CSV 覆盖度</div>
              </div>
              <div ref={indexPopoverRef} className="flex-shrink-0">
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
            </div>

            <UpdateTaskRow
              label="股息率"
              tone={updateState.dividend === 'loading'
                ? 'loading'
                : updateState.dividend === 'success' && updateState.dividend_failed_count !== undefined
                  ? (updateState.dividend_failed_count > 0 ? 'pending' : 'ok')
                  : dividendNeedsUpdate ? 'pending' : 'ok'}
              sub={
                updateState.dividend === 'loading' ? (
                  <span className="text-blue-400">刷新中…</span>
                ) : updateState.dividend === 'success' && updateState.dividend_failed_count !== undefined ? (
                  updateState.dividend_failed_count > 0 ? (
                    <span className="text-amber-400">完成 {updateState.dividend_completed_count} 条，失败 {updateState.dividend_failed_count} 条</span>
                  ) : (
                    <span className="text-green-400">已是最新</span>
                  )
                ) : dividendNeedsUpdate ? (
                  updateState.dividend_target_count ? (
                    <span className="text-amber-400">待完成 {updateState.dividend_target_count - (updateState.dividend_completed_count || 0)}/{updateState.dividend_target_count}</span>
                  ) : (
                    <span className="text-amber-400">本月数据待更新</span>
                  )
                ) : (
                  <span className="text-green-400">已是最新</span>
                )
              }
              actionLabel={updateState.dividend === 'loading' ? '更新中' : '更新'}
              onAction={updateDividend}
              actionDisabled={!dividendNeedsUpdate || updateState.dividend === 'loading'}
            />

            <UpdateTaskRow
              label="辅助数据"
              tone={auxAnyLoading ? 'loading' : auxPendingCount > 0 ? 'pending' : 'ok'}
              sub={
                auxAnyLoading ? (
                  <span className="text-blue-400">更新中…</span>
                ) : auxPendingCount > 0 ? (
                  <span className="text-amber-400">{auxPendingCount} 项待更新</span>
                ) : (
                  <span className="text-green-400">全部最新</span>
                )
              }
              actionLabel={auxAnyLoading ? '更新中' : auxPendingCount > 0 ? '全部更新' : '更新'}
              onAction={updateAllAux}
              actionDisabled={auxAnyLoading || auxPendingCount === 0}
              onToggle={() => setAuxOpen(!auxOpen)}
              expanded={auxOpen}
            >
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
            </UpdateTaskRow>

            <UpdateTaskRow
              label="M120 均线"
              tone={updateState.m120 === 'loading' ? 'loading' : m120NeedsUpdate ? 'pending' : 'ok'}
              sub={
                updateState.m120 === 'loading' ? (
                  <span className="text-blue-400">刷新中…</span>
                ) : m120NeedsUpdate ? (
                  <span className="text-amber-400">有缺失数据</span>
                ) : (
                  <span className="text-green-400">已是最新</span>
                )
              }
              actionLabel={updateState.m120 === 'loading' ? '更新中' : '更新'}
              onAction={() => {
                // 优先传 missing_codes（增量补缺），没有缺失才传全集
                const codesToUpdate = m120MissingCodes.length > 0 ? m120MissingCodes : stockCodes;
                updateM120(codesToUpdate);
                setRefreshKey(k => k + 1);
              }}
              actionDisabled={!m120NeedsUpdate || updateState.m120 === 'loading'}
            />

            <UpdateTaskRow
              label="实时价格"
              tone={updateState.realtime === 'loading' ? 'loading' : 'idle'}
              sub={
                updateState.realtime === 'loading' ? (
                  <span className="text-blue-400">拉取中…</span>
                ) : (
                  '每日更新一次'
                )
              }
              actionLabel={updateState.realtime === 'loading' ? '更新中' : '更新'}
              onAction={() => {
                updateRealtimeInfo(stockCodes);
                setRefreshKey(k => k + 1);
              }}
              actionDisabled={updateState.realtime === 'loading'}
            />
            </div>
            </div>
            </DataUpdateDrawer>
          </div>

          <div className="flex items-center gap-2">
            <div
              className="relative"
              onMouseLeave={() => setExportOpen(false)}
            >
              <button
                onClick={() => setExportOpen(!exportOpen)}
                className="flex items-center gap-2 rounded border border-rule-strong bg-paper-card px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                导出
                <svg className={`w-3 h-3 transition-transform ${exportOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {exportOpen && (
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
                    className="block w-full text-left px-4 py-2 text-sm text-ink hover:bg-paper-tint border-t border-rule"
                  >
                    <div className="font-medium">手机竖版（轮播）</div>
                    <div className="text-xs text-ink-muted mt-0.5">1080×1920 · 支持⬇下载原图</div>
                  </button>
                  <button
                    onClick={downloadCsv}
                    className="block w-full text-left px-4 py-2 text-sm text-ink hover:bg-paper-tint border-t border-rule"
                  >
                    <div className="font-medium">CSV 表格</div>
                    <div className="text-xs text-ink-muted mt-0.5">当前筛选结果 · 全字段</div>
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

      {/* Tab 切换：全部 / 挡位监控；收藏过滤用右侧"只看收藏"按钮 */}
      <div className="flex border-b border-gray-700 mb-4 items-center">
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
        <button onClick={() => handleTabChange('screening')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'screening' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-ink-muted hover:text-ink'}`}>选股关注</button>
        {/* 只看收藏 toggle：仅 all tab 显示，过滤当前列表 */}
        {activeTab === 'all' && (
          <button
            onClick={handleToggleFav}
            className={`ml-auto mb-[-1px] px-3 py-1.5 text-sm rounded-md flex items-center gap-1.5 border transition-colors ${
              favOnly
                ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
                : 'text-yellow-600/80 hover:text-yellow-400 border-transparent hover:border-yellow-500/40 hover:bg-yellow-500/10'
            }`}
            title={favOnly ? '当前仅显示收藏股，点击恢复全部' : '只看收藏的股票'}
          >
            <StarIconOutline className="w-4 h-4" />
            只看收藏
            <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded">{watchlist.total}</span>
          </button>
        )}
      </div>

      {activeTab === 'all' && favOnly && favoriteLoadError && <p role="alert" className="mb-3 text-red-600">收藏资料加载失败：{favoriteLoadError}，暂显示已有资料。</p>}
      {/* 只看收藏 空状态 */}
      {activeTab === 'all' && favOnly && displayData.length === 0 && !loading && (
        <div className="bg-paper-card rounded-lg p-12 text-center">
          <StarIconOutline className="w-12 h-12 mx-auto mb-3 text-gray-500" />
          <p className="text-gray-400 mb-4">
            {watchlist.total === 0 ? '还没有收藏的股票，在列表里点星标添加' : '收藏资料加载中'}
          </p>
          <button
            onClick={handleToggleFav}
            className="text-blue-400 hover:underline text-sm"
          >
            查看全部 →
          </button>
        </div>
      )}

      {/* 表格 - 使用 refreshKey 作为 key 强制刷新；all+favOnly 用过滤后的 displayData */}
      {activeTab === 'screening' ? <ScreeningTab watchlist={watchlist} /> : activeTab === 'alerts' ? (
        <div className="space-y-2">
          {alertStocks.length === 0 ? (
            <div className="bg-paper-card rounded-lg p-12 text-center">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 17l6-6 4 4 8-8M14 7h7v7" />
              </svg>
              <h2 className="text-xl font-semibold text-ink mb-2">暂无设置挡位的收藏股票</h2>
              <p className="text-ink-muted mb-4">去「全部」tab 浏览股票，点星标收藏后设置挡位</p>
              <button
                onClick={() => handleTabChange('all')}
                className="text-blue-400 hover:underline text-sm"
              >
                去全部 tab 浏览 →
              </button>
            </div>
          ) : (
            alertStocks.map(({ stock, levels }) => {
              const price = alertPriceMap.get(stock.code);
              const currentPrice = price?.realtime ?? price?.close ?? null;
              if (currentPrice === null || currentPrice === undefined) return null;
              return (
                <AlertLevelBar
                  key={stock.code}
                  code={stock.code}
                  name={stock.name}
                  levels={levels}
                  currentPrice={currentPrice}
                  currentPE={price?.pe ?? null}
                  currentPB={price?.pb ?? null}
                  dividend2025={stock.dividend_2025 ?? null}
                  yieldTtm={price?.yield_ttm ?? null}
                  priceUpdatedAt={alertPriceUpdatedAt}
                  preClose={price?.close ?? null}
                  onClick={() => handleOpenAlertSettings(stock.code)}
                />
              );
            })
          )}
        </div>
      ) : (
        !(activeTab === 'all' && favOnly && displayData.length === 0) && (
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
