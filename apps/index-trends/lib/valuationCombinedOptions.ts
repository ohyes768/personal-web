/** 估值页合并图的 ECharts 配置（纯函数，可离线测）。
 *
 * 图上只画指数点数一条线（行情）；PB/PE 分位不画走势，改为在 tooltip
 * 里按悬浮日期就近查表显示——分位是估值口径，压在价格图上会让人把
 * 两条线的起伏误读成因果，悬浮查询才是「这个点位时估值贵不贵」的正确读法。
 * x 轴用 time 轴：价格是周频，分位表是日频，各自独立，不摊 category 槽位。
 */
import type { EChartsCoreOption } from "echarts/core";
import type { PriceSeries, ValuationHistory } from "./types";

const COLOR_PRICE = "#2f4858"; // 指数点数：与旧 PriceTrend 同色

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

/** tooltip 里的日期归一：time 轴给毫秒时间戳或 ISO 字符串，统一成 ISO 日期。 */
export function normalizeTooltipDate(value: string | number): string {
  return typeof value === "number"
    ? new Date(value).toISOString().slice(0, 10)
    : String(value).slice(0, 10);
}

/** PB/PE 分位查表：支持「不晚于悬浮日的最近一条」查询。 */
export interface PercentileLookup {
  /** 每条指标各自取不晚于 iso 的最近一条；没有任何更早数据时两侧为 null。 */
  find(iso: string): { pb: number | null; pe: number | null };
  /** 数据覆盖区间（最早 / 最晚日期），空表返回 null。 */
  range(): [string, string] | null;
}

/** 合并 PB 与 PE 两条分位历史为一张查表。
 *
 * 两条序列同源（理杏仁，日频），日期通常一致；单边缺某天时，
 * 查询按各指标自己的最近一条就近取，不因另一条的存在而丢读数。
 */
export function buildPercentileLookup(
  pb: ValuationHistory,
  pe: ValuationHistory,
): PercentileLookup {
  // 每条指标独立存升序日期表，查询各自二分
  const makeSeries = (h: ValuationHistory): { dates: string[]; values: Array<number | null> } => ({
    dates: [...h.dates].sort(),
    values: h.dates
      .map((date, i) => [date, h.percentiles[i] ?? null] as const)
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
      .map(([, v]) => v),
  });
  const pbSeries = makeSeries(pb);
  const peSeries = makeSeries(pe);

  const nearest = (
    dates: string[],
    values: Array<number | null>,
    iso: string,
  ): number | null => {
    let lo = 0;
    let hi = dates.length - 1;
    let hit = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (dates[mid] <= iso) {
        hit = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return hit >= 0 ? (values[hit] ?? null) : null;
  };

  const find = (iso: string): { pb: number | null; pe: number | null } => ({
    pb: nearest(pbSeries.dates, pbSeries.values, iso),
    pe: nearest(peSeries.dates, peSeries.values, iso),
  });

  const range = (): [string, string] | null => {
    const all = [...pbSeries.dates, ...peSeries.dates].sort();
    return all.length > 0 ? [all[0], all[all.length - 1]] : null;
  };
  return { find, range };
}

const fmtPct = (v: number | null | undefined): string =>
  typeof v === "number" ? `${v.toFixed(1)}%` : "—";

/** 估值页 tooltip：悬浮点的指数点数 + 就近日期的 PB/PE 分位。 */
export function formatValuationTooltip(
  date: string,
  price: number | null | undefined,
  lookup: PercentileLookup,
): string {
  const rows: string[] = [`<b>${date}</b>`];
  rows.push(`点数 <b>${typeof price === "number" ? price.toFixed(2) : "—"}</b>`);
  const hit = lookup.find(date);
  rows.push(`PB分位 <b>${fmtPct(hit?.pb)}</b>`);
  rows.push(`PE分位 <b>${fmtPct(hit?.pe)}</b>`);
  return rows.join("<br/>");
}

/** 估值页 option：只画指数点数；PB/PE 分位进 tooltip 查表。 */
export function buildValuationCombinedOption(
  prices: PriceSeries,
  percentileLookup: PercentileLookup,
): EChartsCoreOption {
  const priceData = prices.bars.map((bar) => [bar.date, bar.close] as [string, number]);

  return {
    animation: false,
    // 顶部不再放图例（只有一条线），底部给 dataZoom 与年份标签
    grid: { left: 56, right: 24, top: 16, bottom: 60 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      backgroundColor: "#fffdf8",
      borderColor: "#eadcc9",
      textStyle: { color: "#263329", fontSize: 12 },
      formatter: (params: unknown) => {
        const list = (params ?? []) as Array<{
          value?: [string | number, number | null];
        }>;
        const first = list[0]?.value;
        if (!first) return "";
        return formatValuationTooltip(
          normalizeTooltipDate(first[0]),
          typeof first[1] === "number" ? first[1] : null,
          percentileLookup,
        );
      },
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
    yAxis: {
      // 单轴：指数点数，自适应量程
      type: "value",
      scale: true,
      axisLabel: { color: "#8c6847", fontFamily: "system-ui", fontSize: 10 },
      splitLine: { lineStyle: { color: "#f0e6d4" } },
    },
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
        name: "指数点数",
        type: "line",
        data: priceData,
        showSymbol: false,
        lineStyle: { width: 1.5, color: COLOR_PRICE },
        areaStyle: { color: "rgba(47,72,88,0.06)" },
      },
    ],
  };
}
