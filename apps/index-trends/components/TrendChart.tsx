"use client";

/** 周K + 线性回归通道图（ECharts 按需注册）。
 *
 * 契约（index-trends-echarts spec）：
 * - 空数据不初始化 ECharts 实例；
 * - 隐藏容器（宽高为 0）不初始化，复用已有实例后 setOption(option, true)；
 * - ResizeObserver 处理容器尺寸变化，卸载时 dispose；
 * - dataZoom 只缩放画面，本组件无任何重拟合逻辑（不触发拟合 API）。
 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { CandlestickChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { buildChartAxis, channelValues } from "../lib/candleData";
import {
  emptyWeekNote,
  findWeekIndex,
  isoWeekLabel,
  weekMonth,
  weekRangeLabel,
  weekYear,
} from "../lib/weeks";
import type { ChartData } from "../lib/types";

echarts.use([
  CandlestickChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

interface TrendChartProps {
  data: ChartData;
  chartId: string;
}

const COLOR_UP = "#c0392b"; // 红涨
const COLOR_DOWN = "#2e7d32"; // 绿跌
const COLOR_BAND = "#273f31"; // 上下轨墨绿
const COLOR_MID = "#c56722"; // 中线橙
const COLOR_OBS_BG = "rgba(242,166,90,0.12)"; // 观察区暖黄
const COLOR_FUTURE_BG = "rgba(61,106,133,0.08)"; // 未来延伸区浅蓝

function buildOption(data: ChartData): echarts.EChartsCoreOption {
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

  // 拟合边界可能是该周的周一或周日，两种口径都要能落到同一个 x 轴位置
  const fitEndIndex = (() => {
    const exact = indexByWeek.get(fit_boundary_week);
    if (exact !== undefined) return exact;
    const found = findWeekIndex(categories, fit_boundary_week);
    return found >= 0 ? found : 0;
  })();

  const series: echarts.EChartsCoreOption["series"] = [
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
    {
      name: "中线",
      type: "line",
      data: lineOf(fit_series.weeks, fit_series.mid),
      showSymbol: false,
      lineStyle: { color: COLOR_MID, width: 1.4, type: "dashed" },
      itemStyle: { color: COLOR_MID },
      z: 3,
    },
    {
      name: "中线延伸",
      type: "line",
      data: ext ? lineOf(ext.weeks, ext.mid) : [],
      showSymbol: false,
      lineStyle: { color: COLOR_MID, width: 1.2, type: "dashed" },
      itemStyle: { color: COLOR_MID },
      z: 3,
    },
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
    grid: { left: 64, right: 24, top: 40, bottom: 64 },
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
        const track = (name: string): string => {
          const hit = list.find((p) => p.seriesName === name);
          return hit && typeof hit.value === "number"
            ? `${name} ${hit.value.toFixed(0)}`
            : "";
        };
        const t = [
          track("上轨"),
          track("中线"),
          track("下轨"),
        ].filter(Boolean);
        if (t.length) rows.push(t.join("　"));
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
      chart.setOption(buildOption(data), true);
    };

    render();
    // 隐藏 Tab 变为可见时宽度从 0 变正，这里才真正 init；已有实例只 resize，
    // 避免 setOption 把用户的 dataZoom 缩放重置掉。
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
