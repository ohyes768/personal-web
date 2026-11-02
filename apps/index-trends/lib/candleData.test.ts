import assert from "node:assert/strict";
import test from "node:test";
import { buildChartAxis, channelValues, toCandleDatum } from "./candleData.ts";
import { emptyWeekNote, findWeekIndex, isoWeekLabel, weekRangeLabel } from "./weeks.ts";
import type { ChartBar, ChannelSeries } from "./types.ts";

function bar(weekStart: string, close: number): ChartBar {
  return {
    week_start: weekStart,
    date: weekStart,
    open: close - 10,
    close,
    high: close + 20,
    low: close - 30,
    partial: false,
  };
}

function series(weeks: string[], value: number): ChannelSeries {
  return {
    weeks,
    mid: weeks.map(() => value),
    upper: weeks.map(() => value + 100),
    lower: weeks.map(() => value - 100),
  };
}

test("K 线数据是开收最低最高，不含周序号", () => {
  const datum = toCandleDatum({ open: 3800.5, close: 4041.84, low: 3700, high: 4100 });
  assert.deepEqual(datum, [3800.5, 4041.84, 3700, 4100]);
});

test("没有行情的周用横线占位，不用 null", () => {
  assert.equal(toCandleDatum(undefined), "-");
});

test("ECharts 实际解析保留 OHLC，没有行情的周不绘制蜡烛", async () => {
  const echarts = await import("echarts");
  const chart = echarts.init(null, undefined, {
    renderer: "svg", ssr: true, width: 800, height: 400,
  });
  try {
    chart.setOption({
      xAxis: { type: "category", data: ["2026-10-05", "2026-10-12"] },
      yAxis: { type: "value", scale: true },
      series: [{ type: "candlestick", data: [
        toCandleDatum({ open: 3800.5, close: 4041.84, low: 3700, high: 4100 }),
        toCandleDatum(undefined),
      ] }],
    });
    const data = chart.getModel().getSeriesByIndex(0).getData();
    assert.equal(data.get("open", 0), 3800.5);
    assert.equal(data.get("close", 0), 4041.84);
    assert.equal(data.get("lowest", 0), 3700);
    assert.equal(data.get("highest", 0), 4100);
    assert.equal(Number.isNaN(data.get("open", 1)), true);
    assert.match(chart.renderToSVGString(), /<svg/);
  } finally {
    chart.dispose();
  }
});

test("整周休市保留时间槽但没有 K 线，后续周不被挤掉", () => {
  // 2026-10-05 那一周整周休市：没有行情条目，但时间坐标必须留着
  const weeks = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"];
  const axis = buildChartAxis(
    series(weeks, 4000),
    null,
    [bar("2026-09-28", 3980), bar("2026-10-12", 4010), bar("2026-10-19", 4030)],
  );

  assert.deepEqual(axis.categories, weeks);
  assert.equal(axis.indexByWeek.get("2026-10-05"), 1);
  assert.equal(axis.candleData[1], "-", "休市周必须占位而不是 null");
  assert.equal(axis.indexByWeek.get("2026-10-12"), 2, "休市周不能挤掉后续周的时间槽");
  assert.deepEqual(axis.candleData[2], [4000, 4010, 3980, 4030]);
});

test("未来延伸周用 '-' 占位，且不重复拟合末周", () => {
  const fitWeeks = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"];
  const extWeeks = ["2026-10-19", "2026-10-26", "2026-11-02"];
  const axis = buildChartAxis(
    series(fitWeeks, 4000),
    series(extWeeks, 4100),
    [bar("2026-09-28", 3980), bar("2026-10-05", 3990), bar("2026-10-12", 4010), bar("2026-10-19", 4030)],
  );

  assert.deepEqual(axis.categories, [
    "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02",
  ]);
  assert.equal(axis.candleData[4], "-", "未来周没有行情，必须占位");
  assert.equal(axis.candleData[5], "-");
  assert.equal(axis.candleData[3] !== "-", true, "拟合末周有真实 K 线");
});

test("通道序列摊到整条 x 轴：休市周与未来周留 null，不跨缺口相连", () => {
  const weeks = ["2026-09-28", "2026-10-05", "2026-10-12"];
  const axis = buildChartAxis(series(weeks, 4000), null, []);
  const values = channelValues(weeks, [1, 2, 3], axis.indexByWeek, axis.categories.length);
  assert.deepEqual(values, [1, 2, 3]);

  const extValues = channelValues(["2026-10-19"], [9], axis.indexByWeek, axis.categories.length);
  assert.deepEqual(extValues, [null, null, null], "没有对应分类的周留 null");
});

test("跨年 ISO 周编号正确，年末周不串到下一年", () => {
  assert.equal(isoWeekLabel("2026-12-28"), "2026-W53");
  assert.equal(isoWeekLabel("2027-01-04"), "2027-W01");
  assert.equal(isoWeekLabel("2027-01-11"), "2027-W02");
  assert.equal(weekRangeLabel("2026-12-28"), "2026-12-28 ~ 2027-01-03");
});

test("未来延伸周不叫休市，拟合区内的空槽才是休市", () => {
  assert.equal(
    emptyWeekNote("2026-11-09", "2026-10-26", true),
    "趋势延伸，尚无K线（不是目标价）",
  );
  assert.equal(emptyWeekNote("2026-10-05", "2026-10-26", true), "整周休市，无K线");
  assert.equal(emptyWeekNote("2026-11-09", "2026-10-26", false), "整周休市，无K线");
});

test("拟合边界无论给周一还是周日，都落到同一个自然周位置", () => {
  const weeks = ["2026-12-21", "2026-12-28", "2027-01-04"];
  assert.equal(findWeekIndex(weeks, "2026-12-28"), 1);
  assert.equal(findWeekIndex(weeks, "2027-01-03"), 1, "周日边界属于同一自然周");
  assert.equal(findWeekIndex(weeks, "2026-12-31"), 1);
  assert.equal(findWeekIndex(weeks, "2027-01-04"), 2);
});
