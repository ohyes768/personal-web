/**
 * 夏普曲线图（ECharts 按需注册，Canvas 渲染）
 *
 * 生命周期契约（design「前端设计」，与 index-trends TrendChart 同模式）：
 * - 空数据（无 series / 无 weeks）不渲染容器、不 init 实例
 * - 隐藏容器（宽高为 0）不 init；ResizeObserver 处理尺寸变化；卸载 dispose
 * - 数据变化（weeks/series/minLatestSharpe）→ setOption(option, true) 全量重设
 * - 隐藏集变化（hiddenCodes）→ merge setOption 只更新 legend.selected，
 *   不重置用户的 dataZoom 缩放
 * - 图例点击切换回传父组件（React 为单一真相源），避免图例状态与列表脱节
 *
 * option 构造是纯函数（lib/sharpe-chart.ts），本组件只管实例生命周期。
 */
'use client';

import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import {
  buildSharpeChartOption,
  type SharpeChartSeriesInput,
} from '@/lib/sharpe-chart';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

interface SharpeChartProps {
  weeks: string[];
  series: SharpeChartSeriesInput[];
  minLatestSharpe: number | null;
  /** 数据缺口周（没发榜 / 样本未更新）：竖线标记 + tooltip 提示 */
  gapWeeks: readonly string[];
  /** 图例取消选中的 code 集（父组件持有） */
  hiddenCodes: ReadonlySet<string>;
  /** 图例点击切换回传：code → 是否可见 */
  onLegendChange: (visibleByCode: Record<string, boolean>) => void;
}

export default function SharpeChart({
  weeks,
  series,
  minLatestSharpe,
  gapWeeks,
  hiddenCodes,
  onLegendChange,
}: SharpeChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const hiddenRef = useRef(hiddenCodes);
  hiddenRef.current = hiddenCodes;
  const onLegendChangeRef = useRef(onLegendChange);
  onLegendChangeRef.current = onLegendChange;

  // 数据内容签名：翻页时 weeks/series 引用变化但内容不变（series 不随分页），
  // 依赖签名保持实例存活 → dataZoom 缩放/图例交互状态不被重置
  // （implement 步骤 5：「翻页不重置图状态」）
  const dataSignature = useMemo(
    () => JSON.stringify([weeks, gapWeeks, series.map(s => [s.code, s.values])]),
    [weeks, gapWeeks, series],
  );

  // 数据变化：全量重设 option（含最新 legend.selected）
  useEffect(() => {
    const el = containerRef.current;
    if (!el || series.length === 0 || weeks.length === 0) return;

    const render = () => {
      if (el.clientWidth === 0 || el.clientHeight === 0) return; // 隐藏容器不 init
      const option = buildSharpeChartOption({
        weeks,
        series,
        minLatestSharpe,
        gapWeeks,
        hiddenCodes: hiddenRef.current,
      });
      const existing = echarts.getInstanceByDom(el);
      if (existing) {
        existing.setOption(option, true);
        existing.resize();
        return;
      }
      const chart = echarts.init(el);
      chart.on('legendselectchanged', event => {
        const selected = (event as { selected?: Record<string, boolean> }).selected;
        if (selected) onLegendChangeRef.current(selected);
      });
      chart.setOption(option, true);
    };

    render();
    const observer = new ResizeObserver(() => render());
    observer.observe(el);
    return () => {
      observer.disconnect();
      echarts.getInstanceByDom(el)?.dispose();
    };
  }, [dataSignature, minLatestSharpe]);

  // 隐藏集变化：merge 更新 legend.selected（保留 dataZoom / tooltip 交互状态）
  useEffect(() => {
    const el = containerRef.current;
    const chart = el ? echarts.getInstanceByDom(el) : null;
    if (!chart) return;
    const selected: Record<string, boolean> = {};
    for (const s of series) selected[s.code] = !hiddenCodes.has(s.code);
    chart.setOption({ legend: { selected } }, false);
  }, [hiddenCodes, series]);

  if (series.length === 0 || weeks.length === 0) return null;
  return <div ref={containerRef} className="h-[420px] w-full" aria-label="夏普曲线总图" />;
}
