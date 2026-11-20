import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPercentileLookup,
  buildValuationCombinedOption,
  formatValuationTooltip,
  normalizeTooltipDate,
  yearLabel,
} from "./valuationCombinedOptions.ts";
import type { PriceSeries, ValuationHistory } from "./types.ts";

function history(
  metric: "pb_mcw" | "pe_ttm_mcw",
  dates: string[],
  percentiles: Array<number | null>,
): ValuationHistory {
  return {
    index_code: "399673",
    metric,
    window: "y10",
    dates,
    values: dates.map(() => 1.2),
    percentiles,
  };
}

function prices(dates: string[]): PriceSeries {
  return {
    index_code: "399673",
    name: "创业板50",
    has_channel: false,
    bars: dates.map((date, i) => ({
      week_start: date,
      date,
      close: 1000 + i,
      high: 1010 + i,
      low: 990 + i,
      partial: false,
    })),
    close: dates.length ? 1000 + dates.length - 1 : null,
    price_as_of: dates[dates.length - 1] ?? null,
    data_status: {
      state: "ok",
      data_cutoff_week: null,
      expected_cutoff_week: null,
      expected_close_date: null,
      daily_last_date: null,
      captured_at: null,
      reason: null,
      snapshot_id: null,
    },
    snapshot_id: null,
  };
}

test("查表：悬浮日命中当天；非交易日就近取不晚于悬浮日的一条", () => {
  const pb = history("pb_mcw", ["2024-01-02", "2024-01-05", "2024-01-09"], [10, 20, 30]);
  const pe = history("pe_ttm_mcw", ["2024-01-02", "2024-01-05", "2024-01-09"], [40, 50, 60]);
  const lookup = buildPercentileLookup(pb, pe);

  assert.deepEqual(lookup.find("2024-01-05"), { pb: 20, pe: 50 });
  // 周末（2024-01-06 周六）取周五那条
  assert.deepEqual(lookup.find("2024-01-06"), { pb: 20, pe: 50 });
  // 早于全部数据 → 两侧都 null
  assert.deepEqual(lookup.find("2023-12-31"), { pb: null, pe: null });
  // 区间
  assert.deepEqual(lookup.range(), ["2024-01-02", "2024-01-09"]);
});

test("查表：PB 与 PE 日期不对齐时各取各的，缺失侧为 null", () => {
  const pb = history("pb_mcw", ["2024-01-02", "2024-01-05"], [10, 20]);
  const pe = history("pe_ttm_mcw", ["2024-01-03"], [55]);
  const lookup = buildPercentileLookup(pb, pe);

  assert.deepEqual(lookup.find("2024-01-02"), { pb: 10, pe: null }, "PE 当天没数据");
  // 01-04 悬浮：PB 就近取 01-02（10），PE 就近取 01-03（55）
  assert.deepEqual(lookup.find("2024-01-04"), { pb: 10, pe: 55 }, "各自就近");
});

test("tooltip：点数 + PB/PE 分位两行都显示，不再出现周收盘字样", () => {
  const lookup = buildPercentileLookup(
    history("pb_mcw", ["2024-01-02"], [12.5]),
    history("pe_ttm_mcw", ["2024-01-02"], [55.42]),
  );
  const text = formatValuationTooltip("2024-01-02", 1234.5, lookup);
  assert.match(text, /点数 <b>1234\.50<\/b>/);
  assert.match(text, /PB分位 <b>12\.5%<\/b>/);
  assert.match(text, /PE分位 <b>55\.4%<\/b>/);
  assert.doesNotMatch(text, /周收盘/);
  assert.doesNotMatch(text, /分位走势/);

  const noHit = formatValuationTooltip("2020-01-01", 999, lookup);
  assert.match(noHit, /PB分位 <b>—<\/b>/, "查不到分位显示 —，不渲染 0%");
});

test("option：只画指数点数一条线，没有分位序列与图例", () => {
  const lookup = buildPercentileLookup(
    history("pb_mcw", ["2024-01-02"], [10]),
    history("pe_ttm_mcw", ["2024-01-02"], [40]),
  );
  const option = buildValuationCombinedOption(prices(["2024-01-02", "2024-06-03"]), lookup);

  const series = option.series as Array<{ name: string; data: Array<[string, number]> }>;
  assert.equal(series.length, 1, "只有点数一条线");
  assert.equal(series[0].name, "指数点数");
  assert.equal(option.legend, undefined, "单线不需要图例");
  const yAxis = option.yAxis as { scale?: boolean };
  assert.ok(yAxis.scale, "单轴自适应量程");

  const tooltip = option.tooltip as { formatter: (p: unknown) => string };
  const rendered = tooltip.formatter([
    { value: [new Date("2024-01-02T00:00:00Z").getTime(), 1001] },
  ]);
  assert.match(rendered, /点数 <b>1001\.00<\/b>/);
  assert.match(rendered, /PB分位/, "悬浮要查分位表");
});

test("tooltip 日期归一：毫秒时间戳与 ISO 字符串都行", () => {
  assert.equal(normalizeTooltipDate(new Date("2024-01-02T00:00:00Z").getTime()), "2024-01-02");
  assert.equal(normalizeTooltipDate("2024-01-02"), "2024-01-02");
});

test("十年日频只标每年 1 月的年份", () => {
  assert.equal(yearLabel(new Date("2024-01-02T00:00:00Z").getTime()), "2024");
  assert.equal(yearLabel(new Date("2024-07-01T00:00:00Z").getTime()), "");
  assert.equal(yearLabel("2024-01-02"), "2024");
  assert.equal(yearLabel("2024-12-31"), "");
});

test("样例数据能画出 SVG：点数线与年份标签在画面上，没有分位图例", async () => {
  const echarts = await import("echarts");
  const lookup = buildPercentileLookup(
    history("pb_mcw", ["2024-01-02", "2024-04-01", "2024-07-01"], [80, 60, 40]),
    history("pe_ttm_mcw", ["2024-01-02", "2024-04-01", "2024-07-01"], [70, 50, 30]),
  );
  const option = buildValuationCombinedOption(
    prices(["2024-01-02", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-02"]),
    lookup,
  );
  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 700,
    height: 300,
  });
  try {
    chart.setOption(option);
    const svg = chart.renderToSVGString();
    assert.match(svg, /<svg/);
    assert.match(svg, /2024/, "年份标签要画出来");
    assert.doesNotMatch(svg, /分位/, "图上不再有分位线或图例");
  } finally {
    chart.dispose();
  }
});
