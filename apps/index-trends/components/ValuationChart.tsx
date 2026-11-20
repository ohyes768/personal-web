"use client";

/** 估值合并图：指数点数一条线；PB/PE 分位不画线，悬浮按日期查表显示。
 *
 * 数据由父组件取齐后传入（价格 + 两条分位历史汇成一图）；本组件只管
 * 实例生命周期。契约与 TrendChart 一致：空数据不初始化、复用已有实例后
 * setOption(option, true)、卸载时 dispose。
 * 配置在 lib/valuationCombinedOptions.ts（纯函数，可离线测）。
 */
import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { buildPercentileLookup, buildValuationCombinedOption } from "../lib/valuationCombinedOptions";
import type { PriceSeries, ValuationHistory } from "../lib/types";

echarts.use([
  LineChart,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

interface Props {
  prices: PriceSeries;
  pbHistory: ValuationHistory;
  peHistory: ValuationHistory;
  /** 变化时重建图表内容（切换指数、手动刷新后重画）。 */
  reloadKey: number;
}

export default function ValuationChart({ prices, pbHistory, peHistory, reloadKey }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  // 查表只在两条分位历史变化时重建，不跟随价格刷新抖动
  const lookup = useMemo(() => buildPercentileLookup(pbHistory, peHistory), [pbHistory, peHistory]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || prices.bars.length === 0) {
      chartRef.current?.dispose();
      chartRef.current = null;
      return;
    }
    const chart = chartRef.current ?? echarts.init(host);
    chartRef.current = chart;
    chart.setOption(buildValuationCombinedOption(prices, lookup), true);
  }, [prices, lookup, reloadKey]);

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
