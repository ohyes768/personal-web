"use client";

/** 周K + 线性回归通道图（ECharts 按需注册）。
 *
 * 契约（index-trends-echarts spec）：
 * - 空数据不初始化 ECharts 实例；
 * - 隐藏容器（宽高为 0）不初始化，复用已有实例后 setOption(option, true)；
 * - ResizeObserver 处理容器尺寸变化，卸载时 dispose；
 * - dataZoom 与图例开关只改画面，本组件无任何重拟合逻辑（不触发拟合 API）。
 *
 * 配置本身在 lib/chartOptions.ts（纯函数，可离线测），这里只负责实例生命周期。
 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { CandlestickChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { buildChartOption } from "../lib/chartOptions";
import type { ChartData } from "../lib/types";

echarts.use([
  CandlestickChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

interface TrendChartProps {
  data: ChartData;
  chartId: string;
}

export default function TrendChart({ data, chartId }: TrendChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || data.bars.length === 0) return; // 空数据不初始化

    const render = () => {
      if (el.clientWidth === 0 || el.clientHeight === 0) return; // 隐藏容器不初始化
      const existing = echarts.getInstanceByDom(el);
      if (existing) {
        existing.resize();
        chartRef.current = existing;
        return;
      }
      const chart = echarts.init(el);
      chartRef.current = chart;
      chart.setOption(buildChartOption(data), true);
    };

    render();
    // 隐藏 Tab 变为可见时宽度从 0 变正，这里才真正 init；已有实例只 resize，
    // 避免 setOption 把用户的 dataZoom 缩放与图例开关重置掉。
    const observer = new ResizeObserver(() => render());
    observer.observe(el);
    return () => {
      observer.disconnect();
      echarts.getInstanceByDom(el)?.dispose();
      chartRef.current = null;
    };
  }, [data, chartId]);

  if (data.bars.length === 0) {
    return <div className="empty">暂无可用行情数据</div>;
  }
  return <div ref={containerRef} className="chart-box" />;
}
