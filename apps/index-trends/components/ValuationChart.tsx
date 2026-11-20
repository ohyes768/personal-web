"use client";

/** 估值合并图：周收盘价 + PB/PE 分位画在同一张 ECharts 实例上。
 *
 * 数据由父组件取齐后传入（两个 API 汇合成一图）；本组件只管实例生命周期。
 * 契约与 TrendChart / PercentileChart 一致：空数据不初始化、
 * 复用已有实例后 setOption(option, true)、卸载时 dispose。
 * 配置在 lib/valuationCombinedOptions.ts（纯函数，可离线测）。
 */
import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { buildValuationCombinedOption } from "../lib/valuationCombinedOptions";
import type { PriceSeries, ValuationHistory } from "../lib/types";

echarts.use([
  LineChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

interface Props {
  prices: PriceSeries;
  percentile: ValuationHistory;
  /** 变化时重建图表内容（切换指数、手动刷新后重画）。 */
  reloadKey: number;
}

export default function ValuationChart({ prices, percentile, reloadKey }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || prices.bars.length === 0 || percentile.dates.length === 0) {
      chartRef.current?.dispose();
      chartRef.current = null;
      return;
    }
    const chart = chartRef.current ?? echarts.init(host);
    chartRef.current = chart;
    chart.setOption(buildValuationCombinedOption(prices, percentile), true);
  }, [prices, percentile, reloadKey]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return <div ref={hostRef} className="valuation-canvas" />;
}
