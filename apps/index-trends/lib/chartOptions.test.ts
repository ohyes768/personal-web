import assert from "node:assert/strict";
import test from "node:test";
import { buildChartOption, LEVEL_LINES } from "./chartOptions.ts";
import type { ChannelSeries, ChartBar, ChartData, ModelInfo } from "./types.ts";

const WEEKS = [
  "2026-01-05",
  "2026-01-12",
  "2026-01-19",
  "2026-01-26",
  "2026-02-02",
  "2026-02-09",
];

/** 固定轨道：下轨 300、上轨 500，50% = 400。 */
function channel(): ChannelSeries {
  return {
    weeks: WEEKS,
    mid: WEEKS.map(() => 400),
    upper: WEEKS.map(() => 500),
    lower: WEEKS.map(() => 300),
  };
}

function bar(week: string, close: number): ChartBar {
  return { week_start: week, date: week, open: close, close, high: close, low: close, partial: false };
}

const model: ModelInfo = {
  model_id: "m1",
  index_code: "000300",
  kind: "trailing_10y_weekly",
  timeframe: "week",
  fit_start: WEEKS[0],
  fit_end: WEEKS[WEEKS.length - 1],
  fit_last_trade_date: WEEKS[WEEKS.length - 1],
  sample_count: WEEKS.length,
  calendar_window_start: WEEKS[0],
  calendar_window_end: WEEKS[WEEKS.length - 1],
  data_cutoff_week: WEEKS[WEEKS.length - 1],
  algorithm_version: "lrc-ltb-week-v1",
  multiplier: 2,
  calculated_at: "2026-02-10T00:00:00+08:00",
  coefficients: { slope: 0, intercept: 400, deviation: 50 },
};

/** 收盘位置依次为 5%、10%、90%、95%、15%、10%：两段掉在 30% 线下方。 */
function chartData(): ChartData {
  return {
    model,
    bars: [310, 320, 480, 490, 330, 320].map((close, i) => bar(WEEKS[i], close)),
    fit_series: channel(),
    extension_series: null,
    fit_boundary_week: WEEKS[WEEKS.length - 1],
    extend_note: null,
    snapshot_id: "s1",
  };
}

type Option = ReturnType<typeof buildChartOption>;
type SeriesOption = { name?: string; data?: Array<number | null>; markArea?: { data: unknown[] } };

function seriesOf(option: Option, name: string): SeriesOption {
  const list = option.series as SeriesOption[];
  const found = list.find((s) => s.name === name);
  assert.ok(found, `缺少 series: ${name}`);
  return found;
}

test("三条位置线进图例，名字与 series 对得上", () => {
  const option = buildChartOption(chartData());
  const legend = option.legend as { data: string[] };
  assert.deepEqual(legend.data, LEVEL_LINES.map((p) => `${p}%`));
  for (const position of LEVEL_LINES) {
    assert.ok(seriesOf(option, `${position}%`), `${position}% 线必须在图上`);
  }
});

test("位置线的价格是上下轨之间的插值：50% 即中线", () => {
  const option = buildChartOption(chartData());
  // 下轨 300、上轨 500 → 50% 400、40% 380、30% 360
  assert.deepEqual(seriesOf(option, "50%").data?.slice(0, 1), [400]);
  assert.deepEqual(seriesOf(option, "40%").data?.slice(0, 1), [380]);
  assert.deepEqual(seriesOf(option, "30%").data?.slice(0, 1), [360]);
});

test("30% 线下方着色跟着 30% 线走，其他线不带着色", () => {
  const option = buildChartOption(chartData());
  assert.equal(seriesOf(option, "30%").markArea?.data.length, 2, "两段跌破 30%");
  assert.equal(seriesOf(option, "40%").markArea, undefined);
  assert.equal(seriesOf(option, "50%").markArea, undefined);
  assert.equal(seriesOf(option, "下轨").markArea, undefined);
});

test("没有跌破 30% 时不产生空着色", () => {
  const data = chartData();
  data.bars = [420, 430, 440, 450, 460, 470].map((close, i) => bar(WEEKS[i], close));
  const option = buildChartOption(data);
  assert.equal(seriesOf(option, "30%").markArea, undefined);
});

test("图例开关能单独关掉 30% 线（连带着色），其余线不受影响", async () => {
  const echarts = await import("echarts");
  const option = buildChartOption(chartData());
  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 800,
    height: 400,
  });
  try {
    chart.setOption(option);
    chart.dispatchAction({ type: "legendToggleSelect", name: "30%" });
    const selected = chart.getOption().legend?.[0]?.selected as Record<string, boolean>;
    assert.equal(selected["30%"], false);
    assert.notEqual(selected["50%"], false);
    assert.notEqual(selected["40%"], false);
    assert.match(chart.renderToSVGString(), /<svg/, "关掉一条线仍然正常出图");
  } finally {
    chart.dispose();
  }
});

test("关掉 30% 线时，30% 下方的着色区段也一起从画面消失", async () => {
  const echarts = await import("echarts");
  // 连续 12 周都在 30% 线下方：区段够宽，会被标上名字
  const weeks = Array.from({ length: 12 }, (_, i) => `2026-0${i < 9 ? 1 : 2}-${String(i + 1).padStart(2, "0")}`);
  const data = chartData();
  data.bars = weeks.map((week, i) => bar(week, 320 + i));
  data.fit_series = {
    weeks,
    mid: weeks.map(() => 400),
    upper: weeks.map(() => 500),
    lower: weeks.map(() => 300),
  };
  data.fit_boundary_week = weeks[weeks.length - 1];

  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 800,
    height: 400,
  });
  try {
    chart.setOption(buildChartOption(data));
    assert.match(chart.renderToSVGString(), /30% 以下/, "默认画上着色区段的标注");
    chart.dispatchAction({ type: "legendToggleSelect", name: "30%" });
    assert.doesNotMatch(
      chart.renderToSVGString(),
      /30% 以下/,
      "关掉 30% 线后色块与标注一起收起",
    );
  } finally {
    chart.dispose();
  }
});
