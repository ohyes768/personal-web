import assert from "node:assert/strict";
import test from "node:test";
import {
  buildValuationCombinedOption,
  combinedTooltipFormatter,
  REFERENCE_LEVELS,
  yearLabel,
} from "./valuationCombinedOptions.ts";
import type { PriceSeries, ValuationHistory } from "./types.ts";

function percentile(dates: string[], values: Array<number | null>): ValuationHistory {
  return {
    index_code: "399673",
    metric: "pb_mcw",
    window: "y10",
    dates,
    values: dates.map(() => 1.2),
    percentiles: values,
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

test("分位轴固定 0—100 挂右轴，价格挂左轴，参考线 20/50/80", () => {
  const option = buildValuationCombinedOption(
    prices(["2024-01-02", "2024-06-03"]),
    percentile(["2024-01-02", "2024-06-03", "2024-12-31"], [12.5, 45, null]),
  );
  const yAxes = option.yAxis as Array<{ min?: number; max?: number; position?: string }>;
  assert.equal(yAxes.length, 2);
  assert.notEqual(yAxes[0].min, 0, "价格轴自适应，不固定 0–100");
  assert.equal(yAxes[1].min, 0);
  assert.equal(yAxes[1].max, 100);
  assert.equal(yAxes[1].position, "right");

  const series = option.series as Array<{
    name: string;
    yAxisIndex: number;
    data: Array<[string, number | null]>;
    markLine?: { data: Array<{ yAxis: number }> };
  }>;
  const pct = series.find((s) => s.name === "分位");
  const price = series.find((s) => s.name === "周收盘");
  assert.ok(pct && price, "两条序列都要有");
  assert.equal(pct.yAxisIndex, 1, "分位挂右轴");
  assert.equal(price.yAxisIndex, 0, "价格挂左轴");
  assert.deepEqual(
    pct.markLine?.data.map((d) => d.yAxis),
    [...REFERENCE_LEVELS],
  );
});

test("x 轴是 time 轴：日频分位与周频价格各画各的，不摊 category 槽位", () => {
  const option = buildValuationCombinedOption(
    prices(["2024-01-02"]),
    percentile(["2024-01-02", "2024-01-03", "2024-01-04"], [10, 20, 30]),
  );
  const xAxis = option.xAxis as { type: string };
  assert.equal(xAxis.type, "time");

  const series = option.series as Array<{ data: Array<[string, number | null]> }>;
  assert.equal(series[0].data.length, 3, "分位序列点数 = 分位日期数");
  assert.equal(series[1].data.length, 1, "价格序列点数 = 周数，互不对齐");
});

test("分位 null 断线不补；tooltip 命中什么口径就列什么", () => {
  const option = buildValuationCombinedOption(
    prices(["2024-01-02"]),
    percentile(["2024-01-02"], [null]),
  );
  const series = option.series as Array<{ data: Array<[string, number | null]> }>;
  assert.equal(series[0].data[0][1], null, "缺失分位保持 null，不渲染成 0");

  const both = combinedTooltipFormatter([
    { seriesName: "分位", value: ["2024-01-02", 55.42] },
    { seriesName: "周收盘", value: ["2024-01-02", 1234.5] },
  ]);
  assert.match(both, /55\.4%/);
  assert.match(both, /1234\.50/);
  assert.match(both, /2024-01-02/);

  const onlyPrice = combinedTooltipFormatter([
    { seriesName: "周收盘", value: ["2024-01-02", 1234.5] },
  ]);
  assert.match(onlyPrice, /周收盘/);
  assert.doesNotMatch(onlyPrice, /分位 <b>/, "没命中分位就不列分位行");

  const empty = combinedTooltipFormatter([]);
  assert.equal(empty, "");
});

test("十年日频只标每年 1 月的年份", () => {
  assert.equal(yearLabel("2024-01-02"), "2024");
  assert.equal(yearLabel("2024-12-31"), "");
  assert.equal(yearLabel("2016-01-04"), "2016");
});

test("样例数据能画出 SVG，分位线、价格线与参考线都在画面上", async () => {
  const echarts = await import("echarts");
  const option = buildValuationCombinedOption(
    prices(["2024-01-02", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-02"]),
    percentile(
      ["2024-01-02", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-02"],
      [80, 60, 40, 25, 30],
    ),
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
    assert.match(svg, /80%/, "参考线标签要画出来");
    assert.match(svg, /2024/, "年份标签要画出来");
    assert.match(svg, /分位/, "图例要画出来");
    assert.match(svg, /周收盘/, "图例要画出来");
  } finally {
    chart.dispose();
  }
});
