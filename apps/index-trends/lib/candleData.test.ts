import assert from "node:assert/strict";
import test from "node:test";
import { toCandleDatum } from "./candleData.ts";

test("K 线数据是开收最低最高，不含月份序号", () => {
  const datum = toCandleDatum({ open: 3800.5, close: 4041.84, low: 3700, high: 4100 });
  assert.deepEqual(datum, [3800.5, 4041.84, 3700, 4100]);
});

test("没有行情的月份用横线占位，不用 null", () => {
  assert.equal(toCandleDatum(undefined), "-");
});

test("ECharts 实际解析保留 OHLC，未来月份不绘制蜡烛", async () => {
  const echarts = await import("echarts");
  const chart = echarts.init(null, undefined, {
    renderer: "svg", ssr: true, width: 800, height: 400,
  });
  try {
    chart.setOption({
      xAxis: { type: "category", data: ["2026-09", "2026-10"] },
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
