"use client";

/** 周收盘价格走势：只画价格，不画回归通道。
 *
 * 用于不拟合通道的指数（创业板50）——价格是行情，通道是从价格拟合出来的
 * 另一层东西，两者不绑在一起。
 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { PriceSeries } from "../lib/types";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface Props {
  series: PriceSeries;
  /** 变化时重建图表内容（切换指数、手动刷新后重画）。 */
  reloadKey: number;
}

export default function PriceTrend({ series, reloadKey }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || series.bars.length === 0) {
      chartRef.current?.dispose();
      chartRef.current = null;
      return;
    }
    const chart = chartRef.current ?? echarts.init(host);
    chartRef.current = chart;
    chart.setOption(
      {
        animation: false,
        grid: { left: 52, right: 12, top: 10, bottom: 24 },
        tooltip: {
          trigger: "axis",
          formatter: (params: unknown) => {
            const list = params as Array<{ axisValue: string; data: number }>;
            const item = list?.[0];
            if (!item) return "";
            return `${item.axisValue}<br/>收盘 ${item.data?.toFixed(2) ?? "—"}`;
          },
        },
        xAxis: {
          type: "category",
          data: series.bars.map((bar) => bar.date),
          show: false,
          boundaryGap: false,
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: { fontSize: 10 },
          splitLine: { lineStyle: { color: "#efe6da" } },
        },
        series: [
          {
            type: "line",
            data: series.bars.map((bar) => bar.close),
            showSymbol: false,
            lineStyle: { width: 1.5, color: "#2f4858" },
            areaStyle: { color: "rgba(47,72,88,0.06)" },
          },
        ],
      },
      true,
    );
  }, [series, reloadKey]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return (
    <div className="percentile-chart">
      <div ref={hostRef} className="percentile-canvas" />
    </div>
  );
}
