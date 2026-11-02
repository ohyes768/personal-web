/* eslint-disable @typescript-eslint/no-require-imports -- Node CommonJS test runner installs a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) {
  require.extensions[ext] = (module, filename) => {
    module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
    }).outputText, filename);
  };
}
const { taskBadge, filterNonZero, formatMetrics, relativeTime, absoluteTime } = require('../src/lib/collection-tasks.ts');

test('phase maps to a badge tone and label', () => {
  const expectBadge = (phase, tone, label) => {
    const badge = taskBadge(phase);
    assert.equal(badge.tone, tone, phase);
    assert.equal(badge.label, label, phase);
  };
  for (const phase of ['running', 'crawling', 'publishing', 'checking_sources', 'cancelling']) {
    expectBadge(phase, 'running', '运行中');
  }
  for (const phase of ['succeeded', 'done']) expectBadge(phase, 'ok', '已完成');
  for (const phase of ['partial_failed', 'cooling_down', 'budget_exhausted']) expectBadge(phase, 'warn', '部分完成');
  for (const phase of ['failed', 'error']) expectBadge(phase, 'failed', '失败');
  expectBadge('cancelled', 'idle', '已取消');
  expectBadge('interrupted', 'idle', '已中断');
  expectBadge('idle', 'idle', '尚未采集');
  expectBadge(undefined, 'idle', '尚未采集');
  assert.deepEqual(taskBadge('idle', { idleLabel: '尚未匹配' }), { tone: 'idle', label: '尚未匹配' });
  assert.deepEqual(taskBadge('done', { idleLabel: '尚未匹配' }), { tone: 'ok', label: '已完成' });
  // 后端新增的状态保留原串，只把色调落到 idle。
  assert.deepEqual(taskBadge('brand_new_phase'), { tone: 'idle', label: 'brand_new_phase' });
});

test('zero metrics never reach the surface', () => {
  const metrics = [
    { label: '已检查', value: 0 },
    { label: '已关联', value: 38 },
    { label: '待选择', value: 0 },
    { label: '未找到', value: 3 },
  ];
  assert.deepEqual(filterNonZero(metrics), [
    { label: '已关联', value: 38 },
    { label: '未找到', value: 3 },
  ]);
  assert.equal(filterNonZero([{ label: '查询失败', value: 0 }]).length, 0);
  assert.equal(filterNonZero([{ label: '缺失', value: undefined }]).length, 0);
  assert.equal(filterNonZero([{ label: '缺失', value: null }]).length, 0);
  assert.equal(filterNonZero([{ label: '空', value: '' }]).length, 0);
  assert.equal(filterNonZero([{ label: '零', value: '0' }]).length, 0);
  assert.deepEqual(filterNonZero([{ label: '回退', value: -2 }]), [{ label: '回退', value: -2 }]);
  assert.equal(filterNonZero([]).length, 0);
});

test('metrics render as a compact non-zero list and keep their units', () => {
  const metrics = [
    { label: '已检查', value: 0 },
    { label: '已关联', value: 38 },
    { label: '本次法拍', value: 3, unit: ' 条' },
  ];
  assert.equal(formatMetrics(metrics), '已关联 38 · 本次法拍 3 条');
  assert.equal(formatMetrics([{ label: '已检查', value: 0 }]), '');
  assert.equal(formatMetrics([]), '');
});

test('relative time switches unit at the documented thresholds', () => {
  const now = Date.parse('2026-11-02T12:00:00Z');
  const at = ms => new Date(now - ms).toISOString();
  assert.equal(relativeTime(at(0), now), '刚刚');
  assert.equal(relativeTime(at(59_000), now), '刚刚');
  assert.equal(relativeTime(at(60_000), now), '1 分钟前');
  assert.equal(relativeTime(at(59 * 60_000), now), '59 分钟前');
  assert.equal(relativeTime(at(60 * 60_000), now), '1 小时前');
  assert.equal(relativeTime(at(23 * 3_600_000), now), '23 小时前');
  assert.equal(relativeTime(at(24 * 3_600_000), now), '1 天前');
  assert.equal(relativeTime(at(6 * 86_400_000), now), '6 天前');
  assert.equal(relativeTime(at(7 * 86_400_000), now), '1 周前');
  assert.equal(relativeTime(at(29 * 86_400_000), now), '4 周前');
  assert.equal(relativeTime(at(30 * 86_400_000), now), '1 个月前');
  assert.equal(relativeTime(at(364 * 86_400_000), now), '12 个月前');
  assert.equal(relativeTime(at(365 * 86_400_000), now), '1 年前');
});

test('relative time refuses to invent a value for broken timestamps', () => {
  assert.equal(relativeTime(null), null);
  assert.equal(relativeTime(undefined), null);
  assert.equal(relativeTime(''), null);
  assert.equal(relativeTime('not-a-date'), null);
  assert.equal(absoluteTime(null), null);
  assert.equal(absoluteTime('not-a-date'), null);
});

test('absolute time keeps the Beijing clock so the summary tooltip stays precise', () => {
  // 与 DirectoryCards.tsx 的既有日期格式一致：zh-CN 用斜杠分隔。
  assert.equal(absoluteTime('2026-10-12T00:01:33Z'), '2026/10/12 08:01:33');
});
