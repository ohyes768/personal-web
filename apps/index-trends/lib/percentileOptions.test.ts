import assert from "node:assert/strict";
import test from "node:test";
import { buildPercentileOption, REFERENCE_LEVELS, yearLabel } from "./percentileOptions.ts";
import type { ValuationHistory } from "./types.ts";

function history(dates: string[], percentiles: Array<number | null>): ValuationHistory {
  return {
    index_code: "000300",
    metric: "pb_mcw",
    window: "y10",
    dates,
    values: dates.map(() => 1.2),
    percentiles,
  };
}

test("分位轴固定 0—100，序列直接用后端分位，参考线 20/50/80", () => {
  const option = buildPercentileOption(
    history(["2024-01-02", "2024-06-03", "2024-12-31"], [12.5, 45, null]),
  );
  const yAxis = option.yAxis as { min: number; max: number };
  assert.equal(yAxis.min, 0);
  assert.equal(yAxis.max, 100);

  const series = (option.series as Array<{ data: Array<number | null>; markLine?: { data: Array<{ yAxis: number }> } }>)[0];
  assert.deepEqual(series.data, [12.5, 45, null]);
  assert.deepEqual(
    series.markLine?.data.map((d) => d.yAxis),
    [...REFERENCE_LEVELS],
  );
});

test("十年日频只标每年 1 月的年份", () => {
  assert.equal(yearLabel("2024-01-02"), "2024");
  assert.equal(yearLabel("2024-12-31"), "");
  assert.equal(yearLabel("2016-01-04"), "2016");
});

test("样例数据能画出 SVG，且参考线与年份标签出现在画面上", async () => {
  const echarts = await import("echarts");
  const option = buildPercentileOption(
    history(
      ["2024-01-02", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-02"],
      [80, 60, 40, 25, 30],
    ),
  );
  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 700,
    height: 260,
  });
  try {
    chart.setOption(option);
    const svg = chart.renderToSVGString();
    assert.match(svg, /<svg/);
    assert.match(svg, /50%/, "参考线标签要画出来");
    assert.match(svg, /2024/, "年份标签要画出来");
  } finally {
    chart.dispose();
  }
});
