/**
 * 股息率页面
 * 展示高股息率股票列表及技术指标
 */
'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import { DividendTable } from '@/components/DividendTable';
import { DetailModal } from '@/components/DetailModal';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';
import { CompareDrawer } from '@/components/CompareDrawer';
import { useDividendData, useTechnicalData, useDetailModal, useCompare, useDataUpdate } from '@/lib/hooks';
import type { DividendStock, DividendStockWithTechnical } from '@/lib/types';

const MAX_COMPARE_SELECT = 5;

export default function DividendPage() {
  // 交易所筛选
  const [exchangeFilter, setExchangeFilter] = useState<string>('');
  // 股息率阈值输入
  const [minYieldInput, setMinYieldInput] = useState('3.5');

  // 股息率数据
  const { data, total, loading, error, refetch } = useDividendData();

  // 刷新计数，用于强制表格重新渲染
  const [refreshKey, setRefreshKey] = useState(0);

  // 输出报告下拉菜单开关
  const [reportOpen, setReportOpen] = useState(false);

  // 更新辅助数据下拉菜单开关
  const [auxOpen, setAuxOpen] = useState(false);
  const [auxForce, setAuxForce] = useState(false);

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
  const { state: updateState, m120NeedsUpdate, m120MissingCodes, dividendNeedsUpdate, financialNeedsUpdate, financialMissingCodes, boardMissingCodes, auxStatuses, checkAuxStatus, updateDividend, updateM120, updateRealtimeInfo, updateFinancial, updateSwIndustry, updateShareholder, updateBoard } = useDataUpdate();

  // 抽屉引用
  const drawerRef = useRef<HTMLDivElement>(null);

  // 合并股票数据和技术指标
  const stocksWithTechnical: DividendStockWithTechnical[] = useMemo(() => {
    return data.map(stock => ({
      ...stock,
      technical: technicalData.get(stock.code) || undefined,
    }));
  }, [data, technicalData]);

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
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
        <div className="mb-6">
          <div className="h-8 bg-[#1e222d] rounded w-48 mb-2 animate-pulse"></div>
          <div className="h-5 bg-[#1e222d] rounded w-32 animate-pulse"></div>
        </div>
        <div className="bg-[#1e222d] rounded-lg h-[500px] animate-pulse"></div>
      </div>
    );
  }

  // 空数据提示
  if (!loading && data.length === 0 && !error) {
    return (
      <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
        <div className="mb-6">
          <div className="flex justify-between items-start">
            <div>
              <Link href="/" className="text-[#787b86] hover:text-white transition-colors">
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4 text-[#d1d4dc]">股息率</h1>
            </div>
            <button
              onClick={updateDividend}
              disabled={updateState.dividend === 'loading'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2
                ${updateState.dividend === 'loading'
                  ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
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
        <div className="bg-[#1e222d] rounded-lg p-8 text-center">
          <div className="text-6xl mb-4">📊</div>
          <h2 className="text-xl font-semibold text-[#d1d4dc] mb-2">本月股息率数据未计算</h2>
          <p className="text-[#787b86] mb-6">请点击上方「更新股息率」按钮获取数据</p>
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
    <div className="container mx-auto px-8 lg:px-16 py-8 min-h-screen bg-[#131722]">
      {/* 头部导航 */}
      <div className="mb-6">
        <div className="flex justify-between items-start">
          <div>
            <Link href="/" className="text-[#787b86] hover:text-white transition-colors">
              ← 返回首页
            </Link>
            <h1 className="text-4xl font-bold mt-4 text-[#d1d4dc]">股息率</h1>
            <p className="text-[#787b86] mt-1">
              共 {total} 只股票 | 3年股息率 ≥ {minYieldInput}%
            </p>
            {/* 筛选条件 */}
            <div className="mt-2 flex items-center gap-3">
              <label className="text-sm text-[#787b86]">交易所:</label>
              <select
                value={exchangeFilter}
                onChange={(e) => setExchangeFilter(e.target.value)}
                className="bg-[#2a2e39] text-[#d1d4dc] border border-[#3a3f4b] rounded px-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">全部</option>
                <option value="沪市主板">沪市主板</option>
                <option value="深市主板">深市主板</option>
              </select>
              <label className="text-sm text-[#787b86] ml-2">股息率≥:</label>
              <input
                type="number"
                value={minYieldInput}
                onChange={(e) => setMinYieldInput(e.target.value)}
                className="bg-[#2a2e39] text-[#d1d4dc] border border-[#3a3f4b] rounded px-3 py-1.5 text-sm w-20 focus:outline-none focus:border-indigo-500"
                placeholder="3"
                min="0"
                step="0.1"
              />
              <span className="text-sm text-[#787b86]">%</span>
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
                    ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
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
          <div className="flex items-center gap-2">
            <button
              onClick={updateDividend}
              disabled={!dividendNeedsUpdate || updateState.dividend === 'loading'}
              title={dividendNeedsUpdate ? '本月数据待更新' : '本月数据已更新'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2
                ${!dividendNeedsUpdate || updateState.dividend === 'loading'
                  ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
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
                  更新股息率
                </>
              )}
            </button>

            <div
              className="relative"
              onMouseLeave={() => setAuxOpen(false)}
            >
              <button
                onClick={() => setAuxOpen(!auxOpen)}
                disabled={updateState.sw_industry === 'loading' && updateState.financial === 'loading' && updateState.shareholder === 'loading' && updateState.board === 'loading'}
                className={`
                  px-4 py-2 rounded font-medium transition-all flex items-center gap-2
                  ${updateState.sw_industry === 'loading' || updateState.financial === 'loading' || updateState.shareholder === 'loading' || updateState.board === 'loading'
                    ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
                    : 'bg-indigo-600 text-white hover:bg-indigo-500'
                  }
                `}
              >
                <svg
                  className={`w-4 h-4 ${updateState.sw_industry === 'loading' || updateState.financial === 'loading' || updateState.shareholder === 'loading' || updateState.board === 'loading' ? 'animate-spin' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                {(auxStatuses.sw_industry?.needs_update || auxStatuses.financial?.needs_update || auxStatuses.shareholder?.needs_update || auxStatuses.board?.needs_update) ? '📥 更新辅助数据' : '✅ 已是最新'}
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {auxOpen && (
                <div className="absolute right-0 mt-1 bg-white border border-gray-200 rounded shadow-lg z-50 min-w-[280px]">
                  {[
                    { key: 'sw_industry', label: '申万行业', status: auxStatuses.sw_industry, updateFn: updateSwIndustry, loadingKey: 'sw_industry' as const },
                    { key: 'financial', label: '财务指标', status: auxStatuses.financial, updateFn: (force: boolean) => updateFinancial(financialMissingCodes.length > 0 ? financialMissingCodes : undefined, force), loadingKey: 'financial' as const },
                    { key: 'shareholder', label: '股东户数', status: auxStatuses.shareholder, updateFn: updateShareholder, loadingKey: 'shareholder' as const },
                    { key: 'board', label: '个股板块', status: auxStatuses.board, updateFn: (force: boolean) => updateBoard(boardMissingCodes.length > 0 ? boardMissingCodes : undefined, force), loadingKey: 'board' as const },
                  ].map(item => {
                    const needsUpdate = item.status?.needs_update ?? true;
                    const isLoading = updateState[item.loadingKey] === 'loading';
                    const daysAgo = item.status?.days_since_update != null ? item.status.days_since_update : null;
                    return (
                      <button
                        key={item.key}
                        disabled={isLoading}
                        onClick={async () => {
                          setAuxOpen(false);
                          await item.updateFn(auxForce);
                        }}
                        className="block w-full text-left px-4 py-3 text-sm text-gray-800 hover:bg-indigo-50 border-b border-gray-100 last:border-b-0 first:rounded-t"
                      >
                        <div className="flex items-center gap-2">
                          {isLoading ? (
                            <svg className="w-4 h-4 animate-spin text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          ) : needsUpdate ? (
                            <span>📥</span>
                          ) : (
                            <span>✅</span>
                          )}
                          <span className="font-medium">{item.label}</span>
                        </div>
                        <div className="text-xs text-gray-500 mt-1 ml-6">
                          {item.status?.last_updated
                            ? `上次：${item.status.last_updated}${daysAgo != null ? ` (${daysAgo}天前)` : ''}`
                            : '从未更新'}
                          {item.status?.quarter ? ` · ${item.status.quarter}` : ''}
                        </div>
                      </button>
                    );
                  })}
                  <div className="px-4 py-2 bg-gray-50 border-t border-gray-100">
                    <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={auxForce}
                        onChange={e => setAuxForce(e.target.checked)}
                        className="rounded border-gray-300"
                      />
                      强制刷新（忽略 90 天节流）
                    </label>
                  </div>
                </div>
              )}
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
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2
                ${!m120NeedsUpdate || updateState.m120 === 'loading'
                  ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
              title={m120NeedsUpdate ? "有缺失数据" : "已是最新"}
            >
              <svg
                className={`w-4 h-4 ${updateState.m120 === 'loading' ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              更新M120
            </button>

            <button
              onClick={() => {
                updateRealtimeInfo(stockCodes);
                setRefreshKey(k => k + 1);
              }}
              disabled={updateState.realtime === 'loading'}
              className={`
                px-4 py-2 rounded font-medium transition-all flex items-center gap-2
                ${updateState.realtime === 'loading'
                  ? 'bg-[#2a2e39] text-[#787b86] cursor-not-allowed'
                  : 'bg-indigo-600 text-white hover:bg-indigo-500'
                }
              `}
              title="每日更新一次"
            >
              <svg
                className={`w-4 h-4 ${updateState.realtime === 'loading' ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              更新实时价格
            </button>

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
              className="px-4 py-2 rounded font-medium transition-all flex items-center gap-2 bg-green-600 text-white hover:bg-green-500"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              导出CSV
            </button>

            <div
              className="relative"
              onMouseLeave={() => setReportOpen(false)}
            >
              <button
                onClick={() => setReportOpen(!reportOpen)}
                className="px-4 py-2 rounded font-medium transition-all flex items-center gap-2 bg-blue-600 text-white hover:bg-blue-500"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                输出报告
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {reportOpen && (
                <div className="absolute right-0 mt-1 bg-white border border-gray-200 rounded shadow-lg z-50 min-w-[200px]">
                  <button
                    onClick={() => downloadReport('a4')}
                    className="block w-full text-left px-4 py-2 text-sm text-gray-800 hover:bg-blue-50 first:rounded-t"
                  >
                    <div className="font-medium">A4 一图版（横版）</div>
                    <div className="text-xs text-gray-500 mt-0.5">适合电脑端分享/打印</div>
                  </button>
                  <button
                    onClick={() => downloadReport('carousel')}
                    className="block w-full text-left px-4 py-2 text-sm text-gray-800 hover:bg-blue-50 last:rounded-b border-t border-gray-100"
                  >
                    <div className="font-medium">手机竖版（轮播）</div>
                    <div className="text-xs text-gray-500 mt-0.5">1080×1920 · 支持⬇下载原图</div>
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

      {/* 表格 - 使用 refreshKey 作为 key 强制刷新 */}
      <DividendTable
        key={refreshKey}
        data={stocksWithTechnical}
        technicalData={technicalData}
        onOpenModal={handleOpenModal}
        selectedStockCodes={compare.selectedStocks.map(s => s.code)}
        maxSelect={MAX_COMPARE_SELECT}
        onToggleCompare={handleToggleCompare}
      />

      {/* 详情弹框 */}
      <DetailModal
        isOpen={detailModal.isOpen}
        onClose={detailModal.close}
        type={detailModal.modalType}
        stock={detailModal.stock}
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
