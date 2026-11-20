/** 周K + 线性回归通道的 ECharts 配置（纯函数，不碰 DOM）。
 *
 * 50% / 40% / 30% 三条位置线在价格空间里与轨道平行，由 weeklyPositions 同源的
 * 上下轨插值得到；三条线进 legend，读者可以自己关掉不要的线。30% 线下方的
 * 连续区段挂在 30% 线上，关掉 30% 就连着色一起收起。
 */
import type { EChartsCoreOption } from "echarts/core";
import { buildChartAxis, channelValues } from "./candleData.ts";
import { priceAtPosition, runsBelow, weeklyPositions } from "./channelStats.ts";
import {
  emptyWeekNote,
  findWeekIndex,
  isoWeekLabel,
  weekMonth,
  weekRangeLabel,
  weekYear,
} from "./weeks.ts";
import type { ChartData } from "./types.ts";

const COLOR_UP = "#c0392b"; // 红涨
const COLOR_DOWN = "#2e7d32"; // 绿跌
const COLOR_BAND = "#273f31"; // 上下轨墨绿
const COLOR_MID = "#c56722"; // 50% 中线橙
const COLOR_OBS_BG = "rgba(242,166,90,0.12)"; // 观察区暖黄
const COLOR_FUTURE_BG = "rgba(61,106,133,0.08)"; // 未来延伸区浅蓝
const COLOR_LEVEL = "#a5876a"; // 40%/30% 位置参考线
// 30% 以下区段：向下加深的渐变，读作「跌到这里」而不是「没有数据」
const COLOR_DEEP_BG = {
  type: "linear",
  x: 0,
  y: 0,
  x2: 0,
  y2: 1,
  colorStops: [
    { offset: 0, color: "rgba(39,63,49,0)" },
    { offset: 0.6, color: "rgba(39,63,49,0.06)" },
    { offset: 1, color: "rgba(39,63,49,0.22)" },
  ],
};
const DEEP_LINE = 30; // 图上着色的深度线，与右侧面板的 30% 行同一条线

/** 图上可开关的三条位置线，名字同时是 legend 项与 series 名。 */
export const LEVEL_LINES = [50, 40, 30] as const;

export function buildChartOption(data: ChartData): EChartsCoreOption {
  const { bars, fit_series, extension_series, fit_boundary_week, extend_note } = data;
  const ext = extension_series;
  // 延伸区语义由后端 extend_note 决定：含「非目标价」= 未来投影，否则为历史观察区
  const isFutureExtension = !!ext && !!extend_note && extend_note.includes("非目标价");
  // x 轴 = 拟合区全部自然周 + 延伸区（重复的拟合末周只保留一次）
  const { categories, candleData, indexByWeek, barByWeek } = buildChartAxis(
    fit_series,
    ext,
    bars,
  );

  // 轨道线：fit 段 + 延伸段（缺周补 null，不跨缺口相连）
  const lineOf = (weeks: string[], values: number[]): Array<number | null> =>
    channelValues(weeks, values, indexByWeek, categories.length);

  // 位置线（50%/40%/30%）在价格空间里与轨道平行：对每个分类周取该周的上下轨插值
  const levelValues = (position: number): Array<number | null> => {
    const byWeek = new Map<string, number>();
    for (const series of [fit_series, ext]) {
      if (!series) continue;
      series.weeks.forEach((week, i) => {
        const lower = series.lower[i];
        const upper = series.upper[i];
        if (typeof lower !== "number" || typeof upper !== "number" || upper <= lower) return;
        byWeek.set(week, priceAtPosition(lower, upper, position));
      });
    }
    return categories.map((week) => byWeek.get(week) ?? null);
  };

  const levelLabel = (text: string) => ({
    show: true,
    formatter: text,
    color: "#8c6847",
    fontSize: 10,
  });

  // 30% 线下方的连续区段：与右侧面板同一份位置数据，只在足够宽的区段上标一次名
  const deepAreas = runsBelow(weeklyPositions(bars, fit_series, ext), DEEP_LINE).flatMap(
    (run) => {
      const start = indexByWeek.get(run.start);
      const end = indexByWeek.get(run.end);
      if (start === undefined || end === undefined) return [];
      const endIndex = end > start ? end : Math.min(start + 1, categories.length - 1);
      return [
        [
          { xAxis: categories[start], name: run.weeks >= 8 ? "30% 以下" : "" },
          { xAxis: categories[endIndex] },
        ],
      ];
    },
  );

  // 拟合边界可能是该周的周一或周日，两种口径都要能落到同一个 x 轴位置
  const fitEndIndex = (() => {
    const exact = indexByWeek.get(fit_boundary_week);
    if (exact !== undefined) return exact;
    const found = findWeekIndex(categories, fit_boundary_week);
    return found >= 0 ? found : 0;
  })();

  const series: EChartsCoreOption["series"] = [
    {
      name: "周K",
      type: "candlestick",
      data: candleData,
      itemStyle: {
        color: COLOR_UP,
        color0: COLOR_DOWN,
        borderColor: COLOR_UP,
        borderColor0: COLOR_DOWN,
      },
      barWidth: "62%",
      z: 2,
    },
    {
      name: "上轨",
      type: "line",
      data: lineOf(fit_series.weeks, fit_series.upper),
      showSymbol: false,
      lineStyle: { color: COLOR_BAND, width: 1.6 },
      itemStyle: { color: COLOR_BAND },
      z: 3,
      markLine: {
        silent: true,
        symbol: "none",
        label: {
          show: true,
          formatter: `拟合截止 ${fit_boundary_week}`,
          color: "#8c6847",
          fontSize: 11,
          position: "insideEndTop",
        },
        lineStyle: { color: "#a5876a", type: "solid", width: 1 },
        data: [{ xAxis: fitEndIndex }],
      },
      markArea: ext
        ? {
            silent: true,
            itemStyle: { color: isFutureExtension ? COLOR_FUTURE_BG : COLOR_OBS_BG },
            label: {
              show: true,
              position: "insideTop",
              color: "#8c6847",
              fontSize: 11,
              formatter: isFutureExtension ? "趋势延伸（非预测目标）" : "后续观察区（模型不变）",
            },
            data: [[{ xAxis: categories[fitEndIndex] }, { xAxis: categories[categories.length - 1] }]],
          }
        : undefined,
    },
    {
      name: "上轨延伸",
      type: "line",
      data: ext ? lineOf(ext.weeks, ext.upper) : [],
      showSymbol: false,
      lineStyle: { color: COLOR_BAND, width: 1.4, type: "dashed" },
      itemStyle: { color: COLOR_BAND },
      z: 3,
    },
    // 三条位置线：50% 就是中线，颜色沿用原来的橙虚线；40/30 用细点线
    ...LEVEL_LINES.map((position) => ({
      name: `${position}%`,
      type: "line",
      data: levelValues(position),
      showSymbol: false,
      lineStyle: {
        color: position === 50 ? COLOR_MID : COLOR_LEVEL,
        width: position === 50 ? 1.4 : 1,
        type: position === 50 ? "dashed" : "dotted",
      },
      itemStyle: { color: position === 50 ? COLOR_MID : COLOR_LEVEL },
      endLabel: levelLabel(`${position}%`),
      z: 3,
      // 30% 线下方着色跟着这条线走：关掉开关，色块一起收起
      markArea:
        position === DEEP_LINE && deepAreas.length
          ? {
              silent: true,
              itemStyle: { color: COLOR_DEEP_BG },
              label: {
                show: true,
                position: "insideTop",
                color: "#5f7354",
                fontSize: 10,
                formatter: (params: { name?: string }) => params.name ?? "",
              },
              data: deepAreas,
            }
          : undefined,
    })),
    {
      name: "下轨",
      type: "line",
      data: lineOf(fit_series.weeks, fit_series.lower),
      showSymbol: false,
      lineStyle: { color: COLOR_BAND, width: 1.6 },
      itemStyle: { color: COLOR_BAND },
      z: 3,
    },
    {
      name: "下轨延伸",
      type: "line",
      data: ext ? lineOf(ext.weeks, ext.lower) : [],
      showSymbol: false,
      lineStyle: { color: COLOR_BAND, width: 1.4, type: "dashed" },
      itemStyle: { color: COLOR_BAND },
      z: 3,
    },
  ];

  return {
    animation: false,
    // 右侧留出 50/40/30 端点标签的位置，避免溢出到右栏；顶部留给开关图例
    grid: { left: 64, right: 56, top: 56, bottom: 64 },
    legend: {
      top: 8,
      left: 64,
      itemWidth: 18,
      itemHeight: 2,
      itemGap: 16,
      textStyle: { color: "#8c6847", fontSize: 11, fontFamily: "system-ui" },
      data: LEVEL_LINES.map((position) => `${position}%`),
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", label: { backgroundColor: "#5b4a3a" } },
      backgroundColor: "#fffdf8",
      borderColor: "#eadcc9",
      textStyle: { color: "#263329", fontSize: 12 },
      formatter: (params: unknown) => {
        const list = params as Array<{
          axisValue: string;
          data?: unknown;
          seriesName?: string;
          value?: unknown;
        }>;
        const week = list[0]?.axisValue;
        if (!week) return "";
        const bar = barByWeek.get(week);
        const rows: string[] = [
          `<b>${weekRangeLabel(week)}</b>　${isoWeekLabel(week)}${bar?.partial ? "（进行中）" : ""}`,
        ];
        if (bar) {
          rows.push(
            `开 ${bar.open.toFixed(2)}　收 <b>${bar.close.toFixed(2)}</b><br/>高 ${bar.high.toFixed(2)}　低 ${bar.low.toFixed(2)}`,
          );
          rows.push(`收盘日 ${bar.date}`);
        } else {
          rows.push(emptyWeekNote(week, fit_boundary_week, isFutureExtension));
        }

        // 轨道与位置：位置线可开关，但上下轨始终画在图上，所以用它们反推中线，
        // 关掉 50% 线时这一行仍然成立
        const valueOf = (...names: string[]): number | undefined => {
          for (const name of names) {
            const hit = list.find((p) => p.seriesName === name && typeof p.value === "number");
            if (hit) return hit.value as number;
          }
          return undefined;
        };
        const upper = valueOf("上轨", "上轨延伸");
        const lower = valueOf("下轨", "下轨延伸");
        if (upper !== undefined && lower !== undefined && upper > lower) {
          rows.push(
            `上轨 ${upper.toFixed(0)}　中线 ${((upper + lower) / 2).toFixed(0)}　下轨 ${lower.toFixed(0)}`,
          );
          if (bar) {
            const pct = ((bar.close - lower) / (upper - lower)) * 100;
            rows.push(`位置 <b>${pct.toFixed(1)}%</b>`);
          }
        }
        return rows.join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLine: { lineStyle: { color: "#d7bea0" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#8c6847",
        fontFamily: "system-ui",
        fontSize: 11,
        formatter: (value: string) => {
          // 稀疏标签：每年 1 月显示年份，其余隐藏
          return weekMonth(value) === "01" ? weekYear(value) : "";
        },
      },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#8c6847", fontFamily: "system-ui", fontSize: 11 },
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
    series,
  };
}
