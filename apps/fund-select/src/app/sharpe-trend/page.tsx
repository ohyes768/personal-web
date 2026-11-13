/**
 * 夏普走势独立 Tab（/funds/sharpe-trend?code=xxxxxx，只读现算页面）
 *
 * - 顶部：返回首页 + 标题 + 七 Tab 公共导航（与夏普榜单同模式，不套 FundsHeader）
 * - 无 code：代码输入框引导；有 code：自动加载曲线
 * - KPI 行（稳定性六格）+ 单基金曲线（复用 SharpeChart / buildSharpeChartOption）
 * - 区间切换 all/3y/1y 走 query，不整页刷新；切 code/range 用 AbortController
 *   中止旧请求，防旧响应覆盖新状态
 * - 图表 dynamic(ssr:false) 加载 echarts，仅本页使用
 *
 * 数据口径与「夏普榜单」的区别（design）：
 *   榜单 = 每周冻结的周观测（只在 ≥0.8 入选时记录，有幸存者偏差）；
 *   走势 = 现算完整滚动曲线（跌破 0.8 也看得见）。两者最新值同口径。
 */
'use client';

import { ArrowPathIcon } from '@heroicons/react/24/outline';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';

import { FundsNavigation } from '@/components/FundsNavigation';
import { SharpeTrendStatsPanel } from '@/components/sharpe-trend/SharpeTrendStats';
import {
  DEFAULT_TREND_THRESHOLD,
  FUND_CODE_PATTERN,
  TREND_RANGE_OPTIONS,
  classifySharpeTrend,
  fetchSharpeTrend,
  formatShortDate,
  parseSharpeTrendSearch,
  trendRangeHref,
  type SharpeTrendResponse,
} from '@/lib/sharpe-trend';

const SharpeChart = dynamic(() => import('@/components/sharpe-board/SharpeChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] flex items-center justify-center text-sm text-ink-muted" aria-label="图表加载中">
      图表加载中…
    </div>
  ),
});

function SharpeTrendPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { code, range } = useMemo(
    () => parseSharpeTrendSearch(searchParams), [searchParams],
  );

  const [data, setData] = useState<SharpeTrendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [input, setInput] = useState('');

  // 拉取走势：code/range/reloadTick 变化都中止旧请求
  useEffect(() => {
    if (code === null) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchSharpeTrend(code, range, controller.signal)
      .then(res => {
        if (controller.signal.aborted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : '请求失败，请重试');
        setLoading(false);
      });
    return () => controller.abort();
  }, [code, range, reloadTick]);

  const submitCode = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const v = input.trim();
    if (!FUND_CODE_PATTERN.test(v)) return;
    router.push(trendRangeHref(v, range));
  }, [input, range, router]);

  const phase = classifySharpeTrend(data);

  // 单条 series 适配到复用图表（weeks / values 长度一一对应）
  const weeks = useMemo(
    () => data?.points.map(p => p.date) ?? [],
    [data],
  );
  const series = useMemo(
    () => data && code
      ? [{
          code,
          name: data.name ?? code,
          values: data.points.map(p => p.sharpe),
        }]
      : [],
    [data, code],
  );

  const hasPoint = series.some(s => s.values.some(v => v !== null));

  return (
    <main className="min-h-screen pb-20">
      <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <a href="/" className="text-xs text-ink-muted hover:text-ink-strong transition-colors">
              ← 返回首页
            </a>
            <div className="flex items-baseline gap-3 mt-0.5 flex-wrap">
              <h1 className="text-lg font-semibold text-ink-strong">夏普走势</h1>
              <FundsNavigation active="sharpe-trend" />
            </div>
          </div>
          {data && data.name && (
            <div className="hidden sm:block text-right shrink-0">
              <div className="text-sm font-medium text-ink-strong truncate max-w-[240px]" title={data.name}>
                {data.name}
              </div>
              <div className="text-[11px] text-ink-muted font-mono">{data.code}</div>
            </div>
          )}
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-4 space-y-3">
        {/* 代码输入 + 区间切换 + 口径说明 */}
        <section className="bg-paper-card rounded-lg border border-rule p-3">
          <div className="flex flex-wrap items-center gap-3">
            <form onSubmit={submitCode} className="flex items-center gap-2">
              <label htmlFor="trend-code" className="text-xs text-ink-muted whitespace-nowrap">
                基金代码
              </label>
              <input
                id="trend-code"
                value={input}
                onChange={e => setInput(e.target.value)}
                inputMode="numeric"
                maxLength={6}
                placeholder="6 位代码"
                className="w-28 rounded-lg border border-rule bg-paper-tint px-2.5 py-1.5 text-sm font-mono text-ink-strong focus:outline-2 focus:outline-info"
              />
              <button
                type="submit"
                disabled={!FUND_CODE_PATTERN.test(input.trim())}
                className="px-3 py-1.5 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                查看
              </button>
            </form>

            <div className="flex items-center gap-1" role="group" aria-label="展示区间">
              {TREND_RANGE_OPTIONS.map(opt => (
                <Link
                  key={opt.value}
                  href={code ? trendRangeHref(code, opt.value) : '/sharpe-trend'}
                  aria-current={range === opt.value ? 'true' : undefined}
                  className={`px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                    range === opt.value
                      ? 'bg-accent text-white'
                      : 'text-ink-muted hover:bg-paper-deep hover:text-ink-strong'
                  }`}
                >
                  {opt.label}
                </Link>
              ))}
            </div>

            <span className="text-[11px] text-ink-soft ml-auto" title="现算周频滚动 3 年夏普；不落库、不写入周榜">
              现算 · 每周一点 · 回看 3 年 · 与夏普榜单同口径
            </span>
          </div>
          {code && (
            <div className="mt-2 text-[11px] text-ink-soft">
              也可从股基列表代码、基金详情夏普 KPI、夏普榜单行直接点进来
            </div>
          )}
        </section>

        {/* 无 code：引导态 */}
        {code === null && (
          <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
            <p className="text-sm text-ink-strong">输入基金代码，查看它的夏普走势</p>
            <p className="text-xs text-ink-muted mt-2">
              完整滚动曲线（跌破 0.8 的时段也看得见），用来判断这只基金稳不稳
            </p>
          </section>
        )}

        {/* 错误 / 加载中 */}
        {code !== null && error && (
          <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
            <p className="text-sm text-down">加载失败：{error}</p>
            <button
              type="button"
              onClick={() => setReloadTick(t => t + 1)}
              className="mt-3 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-paper-deep text-sm text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
            >
              <ArrowPathIcon aria-hidden="true" className="h-4 w-4" />
              重试
            </button>
          </section>
        )}
        {code !== null && loading && !data && (
          <div className="h-[420px] animate-pulse" aria-label="加载中">
            <div className="h-full bg-paper-tint rounded-lg" />
          </div>
        )}

        {/* 正常空态：历史不足 / 无有效点 */}
        {!error && !loading && phase === 'insufficient' && (
          <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
            <p className="text-sm text-ink-strong">历史不足，无法计算滚动夏普</p>
            <p className="text-xs text-ink-muted mt-2">
              该基金净值历史少于 250 个交易日（3 年窗口最少需要约 1 年样本）
            </p>
          </section>
        )}
        {!error && !loading && phase === 'no-valid' && (
          <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
            <p className="text-sm text-ink-strong">当前区间没有有效夏普点</p>
            <p className="text-xs text-ink-muted mt-2">切换「全部」区间可查看完整历史</p>
          </section>
        )}

        {/* KPI + 曲线 */}
        {!error && data && phase === 'ok' && (
          <>
            <SharpeTrendStatsPanel
              stats={data.stats}
              rfBasis={data.rf_basis}
              algorithmVersion={data.algorithm_version}
              pointCount={data.points.length}
            />

            <section aria-label="夏普走势曲线" className="bg-paper-card rounded-lg border border-rule">
              <div className="flex flex-wrap items-baseline justify-between gap-2 px-3 pt-3">
                <h2 className="text-sm font-medium text-ink-strong">
                  滚动夏普曲线
                  <span className="ml-2 text-xs font-normal text-ink-muted">
                    每周一点 · 回看 3 年 · 虚线为 {DEFAULT_TREND_THRESHOLD.toFixed(2)} 达标线 · 缺口断线不补零
                  </span>
                </h2>
                <span className="text-[11px] text-ink-soft">
                  {data.points.length > 0 && (
                    <>{formatShortDate(data.points[0].date)} ~ {formatShortDate(data.points[data.points.length - 1].date)}</>
                  )}
                </span>
              </div>
              <div className="px-3 pb-3">
                {hasPoint ? (
                  <SharpeChart
                    weeks={weeks}
                    series={series}
                    minLatestSharpe={DEFAULT_TREND_THRESHOLD}
                    hiddenCodes={new Set<string>()}
                    onLegendChange={() => { /* 单基金无图例联动 */ }}
                  />
                ) : (
                  <div className="h-[420px] flex items-center justify-center text-sm text-ink-muted">
                    所选时间范围内无数据点
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

export default function SharpeTrendPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" aria-label="页面加载中" />}>
      <SharpeTrendPageInner />
    </Suspense>
  );
}
