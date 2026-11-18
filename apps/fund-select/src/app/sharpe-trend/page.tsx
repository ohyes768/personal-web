/**
 * 夏普走势独立 Tab（/funds/sharpe-trend?code=xxxxxx，只读现算页面）
 *
 * - 顶部：返回首页 + 标题 + 七 Tab 公共导航（与夏普榜单同模式，不套 FundsHeader）
 * - 无 code：代码输入框引导；有 code：自动加载曲线
 * - KPI 行（稳定性六格）+ 单基金曲线：复用 components/sharpe-trend/SharpeTrendBody
 *   （列表里点夏普数值弹出的走势弹框也用它，两边样式一样）
 * - 区间切换 all/3y/1y 走 query，不整页刷新；切 code/range 用 AbortController
 *   中止旧请求，防旧响应覆盖新状态
 * - 图表 dynamic(ssr:false) 加载 echarts，仅本页使用
 *
 * 数据口径与「夏普榜单」的区别（design）：
 *   榜单 = 每周冻结的周观测（只在 ≥0.8 入选时记录，有幸存者偏差）；
 *   走势 = 现算完整滚动曲线（跌破 0.8 也看得见）。两者最新值同口径。
 */
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useMemo, useState } from 'react';

import { FundsNavigation } from '@/components/FundsNavigation';
import { SharpeTrendBody } from '@/components/sharpe-trend/SharpeTrendBody';
import {
  FUND_CODE_PATTERN,
  parseSharpeTrendSearch,
  trendRangeHref,
  type SharpeTrendRange,
} from '@/lib/sharpe-trend';
import { useSharpeTrend } from '@/lib/useSharpeTrend';

function SharpeTrendPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { code, range } = useMemo(
    () => parseSharpeTrendSearch(searchParams), [searchParams],
  );

  const { data, loading, error, reload } = useSharpeTrend(code, range);
  const [input, setInput] = useState('');

  const submitCode = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const v = input.trim();
    if (!FUND_CODE_PATTERN.test(v)) return;
    router.push(trendRangeHref(v, range));
  }, [input, range, router]);

  // 区间切换：只改 range，保留 code（客户端导航，不整页刷新）
  const changeRange = useCallback((next: SharpeTrendRange) => {
    if (!code) return;
    router.push(trendRangeHref(code, next));
  }, [code, router]);

  return (
    <main className="min-h-screen pb-20">
      <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <a href="/" className="text-xs text-ink-muted hover:text-ink-strong transition-colors">
              ← 返回首页
            </a>
            <h1 className="text-lg font-semibold text-ink-strong mt-0.5">夏普走势</h1>
            <div className="mt-1">
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
        {/* 代码输入 + 口径说明（区间切换在下方 SharpeTrendBody 内，与弹框同款） */}
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

            <span className="text-[11px] text-ink-soft ml-auto" title="现算周频滚动 3 年夏普；不落库、不写入周榜">
              现算 · 每周一点 · 回看 3 年 · 与夏普榜单同口径
            </span>
          </div>
          {code && (
            <div className="mt-2 text-[11px] text-ink-soft">
              股基列表点「夏普」数值 / 详情夏普卡片可就地弹框；也可从股基列表代码、夏普榜单行进来
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

        {/* 区间切换 + 稳定性 KPI + 滚动夏普曲线（与列表里的走势弹框同款） */}
        {code !== null && (
          <SharpeTrendBody
            data={data}
            loading={loading}
            error={error}
            onRetry={reload}
            range={range}
            onRangeChange={changeRange}
          />
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
