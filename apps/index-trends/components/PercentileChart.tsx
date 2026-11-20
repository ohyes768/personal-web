"use client";

/** 分位历史曲线：一条指标的分位走势（0–100%），带 20/50/80 参考线。
 *
 * 契约与 TrendChart 一致：空数据不初始化实例、隐藏容器不初始化、
 * 复用已有实例后 setOption(option, true)、卸载时 dispose。
 */
import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { api } from "../lib/api";
import type { ValuationMetric } from "../lib/types";

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

interface Props {
  code: string;
  metric: ValuationMetric;
  reloadKey: number;
}

const REFERENCE_LEVELS = [20, 50, 80];

export default function PercentileChart({ code, metric, reloadKey }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .valuationHistory(code, metric)
      .then((history) => {
        if (cancelled) return;
        const host = hostRef.current;
        if (!host || history.dates.length === 0) {
          chartRef.current?.dispose();
          chartRef.current = null;
          setNote("暂无分位历史");
          return;
        }
        const chart = chartRef.current ?? echarts.init(host);
        chartRef.current = chart;
        chart.setOption(
          {
            animation: false,
            grid: { left: 40, right: 10, top: 10, bottom: 22 },
            tooltip: {
              trigger: "axis",
              formatter: (params: unknown) => {
                const list = params as Array<{ axisValue: string; data: number | null }>;
                const item = list?.[0];
                if (!item) return "";
                const value = item.data;
                return `${item.axisValue}<br/>分位 ${
                  typeof value === "number" ? `${value.toFixed(1)}%` : "—"
                }`;
              },
            },
            xAxis: { type: "category", data: history.dates, show: false, boundaryGap: false },
            yAxis: {
              type: "value",
              min: 0,
              max: 100,
              axisLabel: { formatter: "{value}%", fontSize: 10 },
              splitLine: { lineStyle: { color: "#efe6da" } },
            },
            series: [
              {
                type: "line",
                data: history.percentiles,
                showSymbol: false,
                lineStyle: { width: 1.5, color: "#c56722" },
                markLine: {
                  silent: true,
                  symbol: "none",
                  label: { formatter: "{c}%", fontSize: 9, color: "#8c6847" },
                  lineStyle: { type: "dashed", color: "#cbb79f" },
                  data: REFERENCE_LEVELS.map((level) => ({ yAxis: level })),
                },
              },
            ],
          },
          true,
        );
        setNote(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setNote(err instanceof Error ? err.message : "分位历史加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [code, metric, reloadKey]);

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
      {note && <div className="valuation-muted">{note}</div>}
    </div>
  );
}
