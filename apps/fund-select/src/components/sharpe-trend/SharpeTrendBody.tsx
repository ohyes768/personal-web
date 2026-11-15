/**
 * 夏普走势内容区（区间切换 + 稳定性 KPI + 滚动夏普曲线）
 *
 * 夏普走势独立页（/funds/sharpe-trend）与列表里的走势弹框共用本组件，
 * 保证两边「样式一样」：同一套 KPI 卡、同一张图、同样的空态/错误态文案。
 *
 * 数据口径（与「夏普榜单」的区别，design）：
 *   榜单 = 每周冻结的周观测（只在 ≥0.8 入选时记录，有幸存者偏差）；
 *   走势 = 现算完整滚动曲线（跌破 0.8 也看得见）。两者最新值同口径。
 */
'use client';

import { ArrowPathIcon } from '@heroicons/react/24/outline';
import dynamic from 'next/dynamic';
import { useMemo } from 'react';

import {
  DEFAULT_TREND_THRESHOLD,
  TREND_RANGE_OPTIONS,
  classifySharpeTrend,
  formatShortDate,
  type SharpeTrendRange,
  type SharpeTrendResponse,
} from '@/lib/sharpe-trend';

import { SharpeTrendStatsPanel } from './SharpeTrendStats';

/** 图表 dynamic(ssr:false) 加载 echarts，只在真正要画图时才拉包 */
const SharpeChart = dynamic(() => import('@/components/sharpe-board/SharpeChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] flex items-center justify-center text-sm text-ink-muted" aria-label="图表加载中">
      图表加载中…
    </div>
  ),
});

export interface SharpeTrendBodyProps {
  data: SharpeTrendResponse | null;
  loading: boolean;
  error: string | null;
  /** 错误态「重试」 */
  onRetry: () => void;
  range: SharpeTrendRange;
  onRangeChange: (range: SharpeTrendRange) => void;
}

export function SharpeTrendBody({
  data, loading, error, onRetry, range, onRangeChange,
}: SharpeTrendBodyProps) {
  const phase = classifySharpeTrend(data);

  // 单条 series 适配到复用图表（weeks / values 长度一一对应）
  const weeks = useMemo(() => data?.points.map(p => p.date) ?? [], [data]);
  const series = useMemo(
    () => data
      ? [{
          code: data.code,
          name: data.name ?? data.code,
          values: data.points.map(p => p.sharpe),
        }]
      : [],
    [data],
  );

  const hasPoint = series.some(s => s.values.some(v => v !== null));

  return (
    <div className="space-y-3">
      {/* 区间切换（弹框内切按钮；独立页走 router.push，URL 同步 range） */}
      <div className="flex items-center gap-1" role="group" aria-label="展示区间">
        {TREND_RANGE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onRangeChange(opt.value)}
            aria-current={range === opt.value ? 'true' : undefined}
            className={`px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
              range === opt.value
                ? 'bg-accent text-white'
                : 'text-ink-muted hover:bg-paper-deep hover:text-ink-strong'
            }`}
          >
            {opt.label}
          </button>
        ))}
        <span className="text-[11px] text-ink-soft ml-auto" title="现算周频滚动 3 年夏普；不落库、不写入周榜">
          现算 · 每周一点 · 回看 3 年 · 与夏普榜单同口径
        </span>
      </div>

      {/* 错误 */}
      {error && (
        <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
          <p className="text-sm text-down">加载失败：{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-paper-deep text-sm text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
          >
            <ArrowPathIcon aria-hidden="true" className="h-4 w-4" />
            重试
          </button>
        </section>
      )}

      {/* 加载中（还没有旧数据可显示时出骨架） */}
      {loading && !data && (
        <div className="h-[420px] animate-pulse" aria-label="加载中">
          <div className="h-full bg-paper-tint rounded-lg" />
        </div>
      )}

      {/* 正常空态：历史不足 */}
      {!error && !loading && phase === 'insufficient' && (
        <section className="bg-paper-card rounded-lg border border-rule p-8 text-center">
          <p className="text-sm text-ink-strong">历史不足，无法计算滚动夏普</p>
          <p className="text-xs text-ink-muted mt-2">
            该基金净值历史少于 250 个交易日（3 年窗口最少需要约 1 年样本）
          </p>
        </section>
      )}

      {/* 正常空态：区间内没有有效点 */}
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
                  gapWeeks={[]}
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
  );
}
