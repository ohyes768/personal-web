/** 估值合并图的 ECharts 配置（纯函数，可离线测）。
 *
 * 价格走势与 PB/PE 分位画在同一张图上：量纲不同，用双 y 轴——
 * 左轴是周收盘价（行情），右轴是分位 0–100%（估值，主展示）。
 * x 轴用 time 轴：分位历史是日频、价格是周频，两种粒度在同一条时间轴上
 * 各画各的，不摊到同一组 category 槽位。
 *
 * 图例可开关：只想看价格时把分位关掉（反之亦然），两条线互相独立。
 * 分位保留 20/50/80 参考线（与退役前的分位图同源）。
 */
import type { EChartsCoreOption } from "echarts/core";
import type { PriceSeries, ValuationHistory } from "./types";

export const REFERENCE_LEVELS = [20, 50, 80] as const;

const COLOR_PRICE = "#2f4858"; // 周收盘价：与旧 PriceTrend 同色
const COLOR_PERCENTILE = "#c56722"; // 分位：主展示，与旧分位图同色
const COLOR_REF = "#cbb79f"; // 参考线虚线

/** 稀疏年份标签：time 轴标签可能是毫秒时间戳或 ISO 字符串。
 *
 * time 轴的 formatter 收到 number（毫秒时间戳），统一按 UTC 解析成 ISO
 * 再判断；只有 1 月的刻度标年份，其余留空（月刻度全部留白，不标月名）。
 * 重叠交给 axisLabel.hideOverlap。
 */
export function yearLabel(value: string | number): string {
  const text =
    typeof value === "number"
      ? new Date(value).toISOString().slice(0, 10)
      : String(value).slice(0, 10);
  return /^\d{4}-\d{2}/.test(text) ? (text.slice(5, 7) === "01" ? text.slice(0, 4) : "") : "";
}

/** 合并图 tooltip：一行日期，命中什么口径就列什么，参考线固定提示。 */
export function combinedTooltipFormatter(params: unknown): string {
  const list = (params ?? []) as Array<{
    seriesName?: string;
    value?: [string, number | null];
  }>;
  const first = list[0]?.value?.[0];
  if (!first) return "";
  const rows: string[] = [`<b>${first}</b>`];
  for (const item of list) {
    const v = item.value?.[1];
    if (typeof v !== "number") continue;
    if (item.seriesName === "分位") {
      rows.push(`分位 <b>${v.toFixed(1)}%</b>`);
    } else {
      rows.push(`周收盘 <b>${v.toFixed(2)}</b>`);
    }
  }
  return rows.join("<br/>");
}

/** 估值合并图 option：分位为主（右轴 0–100）、周收盘为辅（左轴自适应）。 */
export function buildValuationCombinedOption(
  prices: PriceSeries,
  percentile: ValuationHistory,
): EChartsCoreOption {
  const priceData = prices.bars.map((bar) => [bar.date, bar.close] as [string, number]);
  const pctData = percentile.dates.map(
    (date, i) => [date, percentile.percentiles[i] ?? null] as [string, number | null],
  );

  return {
    animation: false,
    // 顶部留给图例，底部给 dataZoom 与年份标签
    grid: { left: 56, right: 48, top: 40, bottom: 60 },
    legend: {
      top: 6,
      left: 8,
      itemWidth: 18,
      itemHeight: 2,
      itemGap: 16,
      textStyle: { color: "#8c6847", fontSize: 11, fontFamily: "system-ui" },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      backgroundColor: "#fffdf8",
      borderColor: "#eadcc9",
      textStyle: { color: "#263329", fontSize: 12 },
      formatter: combinedTooltipFormatter,
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: "#d7bea0" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#8c6847",
        fontFamily: "system-ui",
        fontSize: 11,
        // 只标月份首刻度的年份：echarts 对 time 轴默认标月名，
        // 用模板把「年-月」压成年份，非年刻度留空；重叠自动隐藏
        formatter: yearLabel,
        hideOverlap: true,
        showMinLabel: true,
        splitNumber: 10,
      },
    },
    yAxis: [
      {
        // 左轴：周收盘价，自适应量程
        type: "value",
        scale: true,
        axisLabel: { color: "#8c6847", fontFamily: "system-ui", fontSize: 10 },
        splitLine: { lineStyle: { color: "#f0e6d4" } },
      },
      {
        // 右轴：分位固定 0–100
        type: "value",
        min: 0,
        max: 100,
        position: "right",
        axisLabel: { formatter: "{value}%", fontSize: 10, color: "#8c6847" },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", start: 0, end: 100 },
      {
        type: "slider",
        height: 18,
        bottom: 12,
        borderColor: "#eadcc9",
        fillerColor: "rgba(231,121,50,0.14)",
        handleStyle: { color: "#e77932" },
        textStyle: { color: "#a5876a", fontSize: 10 },
        dataBackground: {
          lineStyle: { color: "#d7bea0" },
          areaStyle: { color: "rgba(215,190,160,0.3)" },
        },
      },
    ],
    series: [
      {
        // 分位为主展示：画在价格上层
        name: "分位",
        type: "line",
        yAxisIndex: 1,
        data: pctData,
        showSymbol: false,
        lineStyle: { width: 1.5, color: COLOR_PERCENTILE },
        itemStyle: { color: COLOR_PERCENTILE },
        connectNulls: false,
        z: 3,
        markLine: {
          silent: true,
          symbol: "none",
          label: { formatter: "{c}%", fontSize: 9, color: "#8c6847" },
          lineStyle: { type: "dashed", color: COLOR_REF },
          data: REFERENCE_LEVELS.map((level) => ({ yAxis: level })),
        },
      },
      {
        name: "周收盘",
        type: "line",
        yAxisIndex: 0,
        data: priceData,
        showSymbol: false,
        lineStyle: { width: 1.5, color: COLOR_PRICE },
        areaStyle: { color: "rgba(47,72,88,0.06)" },
        z: 2,
      },
    ],
  };
}
