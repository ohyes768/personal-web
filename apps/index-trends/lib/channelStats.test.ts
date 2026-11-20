import assert from "node:assert/strict";
import test from "node:test";
import { channelOccupancy, occupancyOf, priceAtPosition, runsBelow, weeklyPositions } from "./channelStats.ts";
import type { ChartBar, ChannelSeries } from "./types.ts";

function bar(weekStart: string, close: number): ChartBar {
  return {
    week_start: weekStart,
    date: weekStart,
    open: close,
    close,
    high: close,
    low: close,
    partial: false,
  };
}

/** 固定轨道的通道序列：lower 100、upper 300，中线 200。 */
function flat(weeks: string[]): ChannelSeries {
  return {
    weeks,
    mid: weeks.map(() => 200),
    upper: weeks.map(() => 300),
    lower: weeks.map(() => 100),
  };
}

test("通道位置 = (收盘 − 下轨) ÷ (上轨 − 下轨)，下轨 0、上轨 100", () => {
  const positions = weeklyPositions(
    [bar("2026-01-05", 100), bar("2026-01-12", 200), bar("2026-01-19", 300), bar("2026-01-26", 400)],
    flat(["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26"]),
    null,
  );
  assert.deepEqual(
    positions.map((p) => Math.round(p.pct)),
    [0, 50, 100, 150],
  );
});

test("没有收盘价或没有轨道值的周不参与统计", () => {
  const positions = weeklyPositions(
    [bar("2026-01-05", 200), bar("2026-01-19", 250)],
    flat(["2026-01-05", "2026-01-12", "2026-01-19"]),
    null,
  );
  assert.deepEqual(
    positions.map((p) => p.week),
    ["2026-01-05", "2026-01-19"],
  );
});

test("延伸区提供拟合区之后的轨道值", () => {
  const fit = flat(["2026-01-05"]);
  const ext: ChannelSeries = {
    weeks: ["2026-01-05", "2026-01-12"],
    mid: [200, 200],
    upper: [300, 500],
    lower: [100, 300],
  };
  const positions = weeklyPositions(
    [bar("2026-01-05", 200), bar("2026-01-12", 400)],
    fit,
    ext,
  );
  assert.deepEqual(
    positions.map((p) => Math.round(p.pct)),
    [50, 50],
  );
});

test("线下停留占比、最长连续段与当前段", () => {
  const weeks = ["w1", "w2", "w3", "w4", "w5", "w6"];
  const closes = [110, 120, 260, 280, 130, 110]; // 位置 5,10,80,90,15,5
  const positions = weeklyPositions(
    weeks.map((w, i) => bar(w, closes[i])),
    flat(weeks),
    null,
  );

  const stat = occupancyOf(positions, 50);
  assert.equal(stat.belowWeeks, 4);
  assert.equal(stat.totalWeeks, 6);
  assert.equal(Number(stat.share.toFixed(4)), Number((4 / 6).toFixed(4)));
  assert.deepEqual(stat.longest, { start: "w1", end: "w2", weeks: 2 });
  // 并列最长时保留先出现的一段，当前段单独给出
  assert.deepEqual(stat.current, { start: "w5", end: "w6", weeks: 2 });
});

test("最新一周回到线上时没有当前段；从未线下时最长段为空", () => {
  const weeks = ["w1", "w2", "w3"];
  const positions = weeklyPositions(
    [bar(weeks[0], 110), bar(weeks[1], 260), bar(weeks[2], 280)],
    flat(weeks),
    null,
  );
  const stat = occupancyOf(positions, 50);
  assert.equal(stat.belowWeeks, 1);
  assert.deepEqual(stat.longest, { start: "w1", end: "w1", weeks: 1 });
  assert.equal(stat.current, null);

  const none = occupancyOf(positions, 4);
  assert.equal(none.belowWeeks, 0);
  assert.equal(none.longest, null);
});

test("一次算齐 50/40/30 三条线，并给出统计区间与最新位置", () => {
  const weeks = ["2026-01-05", "2026-01-12", "2026-01-19"];
  const result = channelOccupancy(
    [bar("2026-01-05", 120), bar("2026-01-12", 140), bar("2026-01-19", 290)],
    flat(weeks),
    null,
  );
  assert.equal(result.weeks, 3);
  assert.equal(result.spanStart, "2026-01-05");
  assert.equal(result.spanEnd, "2026-01-19");
  assert.equal(Math.round(result.latestPosition ?? 0), 95);
  assert.deepEqual(
    result.stats.map((s) => s.threshold),
    [50, 40, 30],
  );
  // 位置 10、20、95：50 线下 2 周，40 线下 2 周，30 线下 2 周
  assert.deepEqual(
    result.stats.map((s) => s.belowWeeks),
    [2, 2, 2],
  );
});

test("线下连续段按时间先后全部给出，图上分段着色用它", () => {
  const weeks = ["w1", "w2", "w3", "w4", "w5", "w6"];
  const closes = [110, 120, 260, 280, 130, 110]; // 位置 5,10,80,90,15,5
  const positions = weeklyPositions(
    weeks.map((w, i) => bar(w, closes[i])),
    flat(weeks),
    null,
  );
  assert.deepEqual(runsBelow(positions, 40), [
    { start: "w1", end: "w2", weeks: 2 },
    { start: "w5", end: "w6", weeks: 2 },
  ]);
});

test("位置线换算成价格：下轨 0、上轨 100 线性插值", () => {
  assert.equal(priceAtPosition(100, 300, 0), 100);
  assert.equal(priceAtPosition(100, 300, 50), 200);
  assert.equal(priceAtPosition(100, 300, 30), 160);
});

test("空数据不产生统计", () => {
  const result = channelOccupancy([], flat([]), null);
  assert.equal(result.weeks, 0);
  assert.deepEqual(result.stats, []);
  assert.equal(result.latestPosition, null);
});
