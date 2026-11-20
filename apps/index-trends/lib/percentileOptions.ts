/** 分位历史曲线的 ECharts 配置（纯函数，可离线测）。
 *
 * 一条指标的分位走势（0–100%），带 20/50/80 参考线；x 轴是日频日期，
 * 只标每年 1 月的年份，十年序列才不会糊成一片。
 */
import type { EChartsCoreOption } from "echarts/core";
import type { ValuationHistory } from "./types";

export const REFERENCE_LEVELS = [20, 50, 80] as const;

/** 稀疏年份标签：只给每年 1 月的首个样本标年份。 */
export function yearLabel(value: string): string {
  return value.slice(5, 7) === "01" ? value.slice(0, 4) : "";
}

export function buildPercentileOption(history: ValuationHistory): EChartsCoreOption {
  return {
    animation: false,
    grid: { left: 40, right: 10, top: 10, bottom: 26 },
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
    xAxis: {
      type: "category",
      data: history.dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#d7bea0" } },
      axisTick: { show: false },
      axisLabel: {
        show: true,
        color: "#8c6847",
        fontSize: 10,
        formatter: yearLabel,
      },
    },
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
  };
}
