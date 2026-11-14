/**
 * 夏普曲线纯 option 测试（node --experimental-strip-types --test）
 * 锁定 implement.md 步骤 5 的固定断言：完整数据透传、缺席周连线（connectNulls）、单点、下限参考线
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildSharpeChartOption, isolatedPoints } from './sharpe-chart.ts';

test('固定断言：完整数据透传 + connectNulls:true + smooth:false（2026-11-13 改为跨缺席周连线）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-10-19', '2026-10-26', '2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [0.95, null, 1.05] }],
    minLatestSharpe: 1,
  });
  assert.deepEqual(option.series[0].data, [0.95, null, 1.05]);
  assert.equal(option.series[0].connectNulls, true);
  assert.equal(option.series[0].smooth, false);
});

test('缺席周 null 原样透传：数据不补点不补值（连线由 connectNulls 渲染层完成）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-10-19', '2026-10-26', '2026-11-02', '2026-11-09'],
    series: [{ code: '000001', name: 'A', values: [0.9, null, 0.92, null] }],
    minLatestSharpe: null,
  });
  assert.deepEqual(option.series[0].data, [0.9, null, 0.92, null]);
});

test('isolatedPoints：单点段标记孤立，连续段不标记', () => {
  // A=[0.95, 缺席, 1.05]：两个点各自孤立（AC2 的中间断线、单点可见）
  assert.deepEqual(isolatedPoints([0.95, null, 1.05]), [true, false, true]);
  // 连续两点互相为邻居
  assert.deepEqual(isolatedPoints([0.9, 0.92, null]), [false, false, false]);
  // 全缺席无孤立点
  assert.deepEqual(isolatedPoints([null, null]), [false, false]);
  // 空序列
  assert.deepEqual(isolatedPoints([]), []);
});

test('单点可见：孤立点 symbolSize>0，连续点 symbolSize=0（不铺满画布）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-10-19', '2026-10-26', '2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [0.95, null, 1.05] }],
    minLatestSharpe: null,
  });
  const spec = option.series[0];
  assert.equal(spec.showSymbol, true);
  assert.equal(spec.symbolSize(null, { dataIndex: 0 }), 4);
  assert.equal(spec.symbolSize(null, { dataIndex: 2 }), 4);
  assert.equal(
    spec.symbolSize(null, { dataIndex: 1 }),
    0,
    '缺席位置不应显示 symbol',
  );
  // 连续段内的点不显 symbol
  const continuous = buildSharpeChartOption({
    weeks: ['2026-10-19', '2026-10-26'],
    series: [{ code: '000001', name: 'A', values: [0.9, 0.92] }],
    minLatestSharpe: null,
  });
  assert.equal(continuous.series[0].symbolSize(null, { dataIndex: 0 }), 0);
  assert.equal(continuous.series[0].symbolSize(null, { dataIndex: 1 }), 0);
});

test('夏普下限参考线：minLatestSharpe 挂在第一条 series 的 markLine', () => {
  const withLine = buildSharpeChartOption({
    weeks: ['2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [1.05] }],
    minLatestSharpe: 1,
  });
  const markLine = withLine.series[0].markLine as { data?: Array<{ yAxis?: number }> } | undefined;
  assert.equal(markLine?.data?.[0]?.yAxis, 1);

  const withoutLine = buildSharpeChartOption({
    weeks: ['2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [1.05] }],
    minLatestSharpe: null,
  });
  assert.equal(withoutLine.series[0].markLine, undefined);
});

test('纵轴不强制从零：yAxis.scale = true', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [0.9] }],
    minLatestSharpe: null,
  });
  assert.equal(option.yAxis.scale, true);
});

test('全部命中基金进图：series 不按列表分页截断（AC10）', () => {
  const input = {
    weeks: ['2026-10-19', '2026-10-26', '2026-11-02'],
    series: [
      { code: '000001', name: 'A', values: [0.95, null, 1.05] },
      { code: '000002', name: 'B', values: [0.9, 0.92, 0.94] },
      { code: '000003', name: 'C', values: [null, null, 0.88] },
    ],
    minLatestSharpe: null,
  };
  const option = buildSharpeChartOption(input);
  assert.equal(option.series.length, 3);
  assert.deepEqual(
    option.series.map(s => s.name),
    ['000001', '000002', '000003'],
  );
  // 图例覆盖全部命中基金
  assert.equal(option.legend.data.length, 3);
  // 未传 hiddenCodes 时全部可见
  assert.deepEqual(option.legend.selected, { '000001': true, '000002': true, '000003': true });
});

test('hiddenCodes → legend.selected（图例隐藏/列表聚焦联动）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-11-02'],
    series: [
      { code: '000001', name: 'A', values: [1.05] },
      { code: '000002', name: 'B', values: [0.94] },
    ],
    minLatestSharpe: null,
    hiddenCodes: new Set(['000002']),
  });
  assert.deepEqual(option.legend.selected, { '000001': true, '000002': false });
});

test('x 轴为统一周历：categories 与 weeks 逐字一致', () => {
  const weeks = ['2026-10-19', '2026-10-26', '2026-11-02'];
  const option = buildSharpeChartOption({
    weeks,
    series: [{ code: '000001', name: 'A', values: [0.95, null, 1.05] }],
    minLatestSharpe: null,
  });
  assert.deepEqual(option.xAxis.data, weeks);
});

// ── 数据缺口周标记（11-14-sharpe-board-gap-weeks）─────────────────────────────

test('数据缺口周：竖线标记挂在 markLine（与下限线共存）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-02-09', '2026-02-16', '2026-02-23'],
    series: [{ code: '000001', name: 'A', values: [0.9, null, 0.92] }],
    minLatestSharpe: 0.8,
    gapWeeks: ['2026-02-16'],
  });
  const markLine = option.series[0].markLine as
    | { data?: Array<{ xAxis?: string; yAxis?: number }> }
    | undefined;
  assert.equal(markLine?.data?.length, 2);
  assert.equal(markLine?.data?.[0]?.yAxis, 0.8);          // 下限线在前
  assert.equal(markLine?.data?.[1]?.xAxis, '2026-02-16'); // 缺口周竖线
});

test('无缺口周 → 不画标记；只有缺口周时仍要出标记', () => {
  const none = buildSharpeChartOption({
    weeks: ['2026-11-02'],
    series: [{ code: '000001', name: 'A', values: [1.05] }],
    minLatestSharpe: null,
  });
  assert.equal(none.series[0].markLine, undefined);

  const gapOnly = buildSharpeChartOption({
    weeks: ['2026-02-16'],
    series: [{ code: '000001', name: 'A', values: [null] }],
    minLatestSharpe: null,
    gapWeeks: ['2026-02-16'],
  });
  const markLine = gapOnly.series[0].markLine as
    | { data?: Array<{ xAxis?: string }> }
    | undefined;
  assert.equal(markLine?.data?.length, 1);
  assert.equal(markLine?.data?.[0]?.xAxis, '2026-02-16');
});

test('tooltip：缺口周单独提示（不误报「本周无在榜记录」）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-02-16', '2026-02-23'],
    series: [{ code: '000001', name: 'A', values: [null, 0.92] }],
    minLatestSharpe: null,
    gapWeeks: ['2026-02-16'],
  });
  const fmt = option.tooltip.formatter as (p: unknown) => string;
  const gapHtml = fmt([{ seriesName: '000001', value: null, axisValue: '2026-02-16' }]);
  assert.match(gapHtml, /数据缺口周/);
  assert.doesNotMatch(gapHtml, /本周无在榜记录/);
  // 普通无数据周仍是原话术
  const normalHtml = fmt([{ seriesName: '000001', value: null, axisValue: '2026-02-23' }]);
  assert.match(normalHtml, /本周无在榜记录/);
});

test('标注挂在第一条可见 series（图例隐藏的 series 不绘制 markLine）', () => {
  const option = buildSharpeChartOption({
    weeks: ['2026-02-16'],
    series: [
      { code: '000001', name: 'A', values: [null] },
      { code: '000002', name: 'B', values: [null] },
    ],
    minLatestSharpe: null,
    gapWeeks: ['2026-02-16'],
    hiddenCodes: new Set(['000001']),
  });
  assert.equal(option.series[0].markLine, undefined);
  assert.ok(option.series[1].markLine, '标记应挂在第一条可见曲线上');
});
