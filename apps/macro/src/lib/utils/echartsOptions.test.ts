import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildLineTrace, lastValidDate, type ChartLayout } from './chartTheme';
import { buildEChartsOption, chartDates, clampRange, dateRangeFromZoom, tooltipLines } from './echartsOptions';
const dates = ['2026-10-01', '2026-10-02', '2026-10-03'];
const left = buildLineTrace({ id: 'cn_10y', label: '中国10y', color: '#f00', unit: '%', yaxis: 'y3' }, dates, [2, null, 2.1])!;
const right = buildLineTrace({ id: 'spread', label: '利差', color: '#00f', unit: '%', yaxis: 'y4' }, dates, [.4, .3, .2])!;
const layout: ChartLayout = { axes: [
  { key: 'y3', title: '10y (%)', axisColor: '#f00' },
  { key: 'y4', title: '利差 (%)', axisColor: '#00f', side: 'right', range: [-1, 1] },
] };
test('dual axes preserve sparse observations rather than joining missing dates', () => {
  const option = buildEChartsOption([left, right], layout, null);
  assert.ok(Array.isArray(option.series));
  const lines = option.series;
  assert.deepEqual(lines[0].data, [2, null, 2.1]);
  assert.equal(lines[0].type, 'line');
  assert.equal('connectNulls' in lines[0] && lines[0].connectNulls, false);
  assert.equal('yAxisIndex' in lines[1] && lines[1].yAxisIndex, 1);
  assert.ok(Array.isArray(option.yAxis));
  assert.equal(option.yAxis[1].position, 'right');
  assert.equal(option.yAxis[1].min, -1);
});
test('all-empty and non-finite series stay empty; short series have visible markers', () => {
  assert.equal(buildLineTrace({ id: 'empty', label: '空', color: '#fff' }, dates, [null, NaN, Infinity]), null);
  assert.equal(left.markers, true);
  assert.equal(lastValidDate([left]), '2026-10-03');
});
test('different source date sets align by date without filling gaps', () => {
  const other = buildLineTrace({ id: 'other', label: '另一个', color: '#fff' }, ['2026-10-02', '2026-10-04'], [3, 4])!;
  const option = buildEChartsOption([left, other], layout, null);
  assert.deepEqual(chartDates([left, other]), [...dates, '2026-10-04']);
  assert.ok(Array.isArray(option.series));
  assert.deepEqual(option.series[1].data, [null, 3, null, 4]);
});
test('zoom maps to observations and reset is an explicit null range', () => {
  assert.deepEqual(dateRangeFromZoom(dates, 50, 100), ['2026-10-02', '2026-10-03']);
  assert.equal(dateRangeFromZoom(dates, 0, 100), null);
  assert.equal(dateRangeFromZoom([], 20, 80), null);
  assert.deepEqual(clampRange(dates, ['2026-09-01', '2026-10-02']), ['2026-10-01', '2026-10-02']);
});
test('normalized tooltip retains original units and change', () => {
  const line = buildLineTrace({ id: 'fx', label: '汇率', color: '#fff', transform: 'normalize' }, dates, [100, 101, null], {
    details: [{ label: '原始值', values: [7, 7.07, null], decimals: 4 }, { label: '涨跌', values: [0, 1, null], unit: '%', decimals: 2 }],
  })!;
  assert.deepEqual(tooltipLines(line, dates[1]), ['汇率：101.00', '原始值：7.0700', '涨跌：1.00 %']);
  assert.equal(line.transform, 'normalize');
});
test('option generation does not mutate shared range or series', () => {
  const range: [string, string] = [dates[1], dates[2]];
  const before = JSON.stringify([left, range]);
  buildEChartsOption([left], layout, range, true);
  assert.equal(JSON.stringify([left, range]), before);
});

test('short zoom windows remain ordered and date labels align inside the grid', () => {
  const range = dateRangeFromZoom(dates, 49, 51);
  assert.deepEqual(range, ['2026-10-02', '2026-10-02']);
  const option = buildEChartsOption([left], layout, range, true);
  assert.ok(option.xAxis && !Array.isArray(option.xAxis));
  assert.equal(option.xAxis.axisLabel?.alignMaxLabel, 'right');
  assert.equal(option.xAxis.axisLabel?.showMaxLabel, true);
});

test('empty chart has no orphan axes or dataZoom components', () => {
  const option = buildEChartsOption([], { axes: [] }, null);
  assert.deepEqual(option, { series: [], xAxis: [], yAxis: [], dataZoom: [] });
});
