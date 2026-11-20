"use client";

/** 分位历史曲线：一条指标的分位走势（0–100%），带 20/50/80 参考线。
 *
 * 契约与 TrendChart 一致：空数据不初始化实例、隐藏容器不初始化、
 * 复用已有实例后 setOption(option, true)、卸载时 dispose。
 * 配置在 lib/percentileOptions.ts（纯函数，可离线测）。
 */
import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { api } from "../lib/api";
import { buildPercentileOption } from "../lib/percentileOptions";
import type { ValuationMetric } from "../lib/types";

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

interface Props {
  code: string;
  metric: ValuationMetric;
  reloadKey: number;
}

export default function PercentileChart({ code, metric, reloadKey }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // 没有数据时不占着 260px 的空白画布（宿主节点要一直在，否则恢复后无处 init）
  const [hasData, setHasData] = useState(false);

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
          setHasData(false);
          setNote("暂无分位历史");
          return;
        }
        const chart = chartRef.current ?? echarts.init(host);
        chartRef.current = chart;
        chart.setOption(buildPercentileOption(history), true);
        setNote(null);
        setHasData(true);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setHasData(false);
          setNote(err instanceof Error ? err.message : "分位历史加载失败");
        }
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
      <div ref={hostRef} className={`percentile-canvas${hasData ? "" : " is-empty"}`} />
      {note && <div className="valuation-muted">{note}</div>}
    </div>
  );
}
