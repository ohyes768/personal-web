/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup: render } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { PositionBadge, default: PositionPanel } = require('../src/components/community/PositionPanel.tsx');
const { CatalogTable, CollectionControls } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

test('history coordinates are distinct from a matched POI and missing coordinates', () => {
  const html = render(React.createElement(PositionBadge, { position: { state: 'pending', has_coordinates: true, candidates: [] } }));
  assert.match(html, /待补全/); assert.match(html, /已有地图坐标/); assert.match(html, /历史坐标不代表已匹配 POI/);
  assert.doesNotMatch(html, /缺少地图坐标/);
  const missing = render(React.createElement(PositionBadge, { position: { state: 'pending', has_coordinates: false, candidates: [] } }));
  assert.match(missing, /缺少地图坐标/); assert.doesNotMatch(missing, /已有地图坐标/);
});
test('admitted rows show independent POI status and review action', () => {
  const html = render(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '测试花园', map_status: 'displayed', position: { state: 'review', has_coordinates: true, candidates: [] } }] }));
  assert.match(html, /高德定位/); assert.match(html, /地图显示/); assert.match(html, /待确认/); assert.match(html, /确认位置/);
});
test('candidate panel preserves evidence, stale-write revision and manual protection', () => {
  const html = render(React.createElement(PositionPanel, { busy: false, query() {}, confirm() {}, position: {
    state: 'review', revision: 'abc', has_coordinates: true, checked_at: '2026-10-16T01:00:00Z', error: '候选地址不同，请核对',
    candidates: [{ source_id: 'B1', name: '风雅钱塘', address: '月明路1076号', longitude: 120.207, latitude: 30.202, source_url: 'https://www.amap.com/search?query=test' }]
  } }));
  assert.match(html, /高德定位 · 待确认/); assert.match(html, /月明路1076号/); assert.match(html, /POI B1/);
  assert.match(html, /确认所选位置/); assert.match(html, /手动定位/); assert.match(html, /GCJ02/); assert.match(html, /候选地址不同/);
  const manual = render(React.createElement(PositionPanel, { busy: false, query() {}, confirm() {}, position: {
    state: 'manual', revision: 'abc', has_coordinates: true, candidates: [], selected: { longitude: 120.207, latitude: 30.202 }
  } }));
  assert.match(manual, /人工结果已保护/); assert.match(manual, /人工坐标，无 POI ID/); assert.doesNotMatch(manual, /重新匹配/);
});
test('amap job summary reports per-outcome states instead of skip counts', () => {
  const html = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, action() {}, errors: {}, jobs: { amap: {
    running: false, phase: 'succeeded', processed: 155, total: 155, updated: 1, skipped: 102,
    review: 24, not_found: 29, failed: 0, skipped_by_state: { manual: 2, review: 71, not_found: 29 } } } }));
  assert.match(html, /采集完成/);
  assert.match(html, /补全 1 · 转待确认 24 · 高德无此地点 29/);
  assert.match(html, /已处理 155 \/ 155/);
  assert.match(html, /未参与本轮 102/);
  assert.match(html, /人工已确认 2 · 待确认 71 · 未找到 29/);
  assert.doesNotMatch(html, /跳过/);
});
test('legacy amap job without outcome fields keeps the old wording', () => {
  const html = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, action() {}, errors: {}, jobs: { amap: {
    running: false, phase: 'partial_failed', processed: 155, total: 155, updated: 0, skipped: 155 } } }));
  assert.match(html, /部分完成/);
  assert.match(html, /补全 0 · 跳过 155/);
});
