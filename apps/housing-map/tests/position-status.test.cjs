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
test('admitted rows show one position column matching the filter and review action', () => {
  const html = render(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '测试花园', map_status: 'displayed', position: { state: 'review', has_coordinates: true, candidates: [] } }] }));
  assert.match(html, /高德定位/); assert.doesNotMatch(html, /地图定位|地图显示/); assert.match(html, /待确认/); assert.match(html, /确认位置/);
  assert.equal((html.match(/<th>高德定位<\/th>/g) || []).length, 1);
});

test('compact position badges use the same three categories as the filter', () => {
  for (const [state, label] of [['matched', '已定位'], ['manual', '已定位'], ['review', '待确认'],
    ['pending', '待处理'], ['not_found', '待处理'], ['error', '待处理']]) {
    const html = render(React.createElement(PositionBadge, { compact: true, position: { state, has_coordinates: true, candidates: [] } }));
    assert.ok(html.includes(`>${label}</span>`), `${state} should display ${label}`);
  }
});

test('candidate panel preserves evidence, stale-write revision and manual protection', () => {
  const html = render(React.createElement(PositionPanel, { busy: false, query() {}, confirm() {}, position: {
    state: 'review', revision: 'abc', has_coordinates: true, checked_at: '2026-10-16T01:00:00Z', error: '候选地址不同，请核对',
    candidates: [{ source_id: 'B1', name: '风雅钱塘', address: '月明路1076号', longitude: 120.207, latitude: 30.202, source_url: 'https://www.amap.com/search?query=test' }]
  } }));
  assert.match(html, /<h4>高德定位<\/h4>/); assert.match(html, />待确认<\/span>/); assert.match(html, /<option value="B1">风雅钱塘 · 月明路1076号<\/option>/);
  assert.match(html, /<select aria-label="选择高德候选位置"/);
  assert.match(html, /<button[^>]*disabled="">确认位置/);
  assert.doesNotMatch(html, /手动定位|手动地图地址|手动经度|手动纬度|填写坐标|type="radio"|重新匹配|补全高德 POI/); assert.match(html, /候选地址不同/);
  const manual = render(React.createElement(PositionPanel, { busy: false, query() {}, confirm() {}, position: {
    state: 'manual', revision: 'abc', has_coordinates: true, candidates: [], selected: { longitude: 120.207, latitude: 30.202 }
  } }));
  assert.match(manual, /<h4>高德定位<\/h4>[^]*>已定位<\/span>/);
  assert.doesNotMatch(manual, /<details|POI ID|GCJ02|最近查询|人工确认：|定位状态：|重新匹配/);
});

test('only review positions expose candidate selection; other states have no single retry action', () => {
  for (const state of ['pending', 'matched', 'manual', 'error', 'not_found']) {
    const position = { state, revision: 'abc', has_coordinates: true,
      candidates: [{ source_id: 'B1', name: '测试花园', address: '测试路1号' }] };
    const panel = render(React.createElement(PositionPanel, { position, busy: false, confirm() {} }));
    assert.doesNotMatch(panel, /<select|<button|手动定位/);
    const row = render(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
      items: [{ community_id: '1', community_name: '测试花园', position }] }));
    assert.doesNotMatch(row, /查看定位|补全 \/ 重试|确认位置/);
  }
});

test('candidate confirmation is blocked while busy or missing a revision', () => {
  for (const extra of [{ busy: true, revision: 'abc' }, { busy: false, revision: undefined }]) {
    const html = render(React.createElement(PositionPanel, { busy: extra.busy, confirm() {}, position: {
      state: 'review', revision: extra.revision, has_coordinates: false,
      candidates: [{ source_id: 'B1', name: '测试花园', address: '测试路1号' }, { source_id: 'B2', name: '地址缺失' }]
    } }));
    assert.match(html, /<select[^>]*disabled=""/);
    assert.match(html, /<option value="B2" disabled=""/);
    assert.match(html, /<button[^>]*disabled="">确认位置/);
  }
});
test('amap job summary reports per-outcome states instead of skip counts', () => {
  const html = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, action() {}, errors: {}, jobs: { amap: {
    running: false, phase: 'succeeded', processed: 155, total: 155, updated: 1, skipped: 102,
    review: 24, not_found: 29, failed: 0, skipped_by_state: { manual: 2, review: 71, not_found: 29 } } } }));
  assert.match(html, /采集完成/);
  assert.match(html, /补全 1 · 待人工确认 24 · 未找到主体地点 29/);
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


test('matched position shows address and safe source directly, with a name only when different', () => {
  const props = { busy: false, confirm() {}, communityName: '茂御居', position: {
    state: 'matched', has_coordinates: true, candidates: [], checked_at: '2026-10-16T04:04:28Z',
    selected: { name: '茂御居', source_id: 'B0K13CUM4W', address: '江南大道', longitude: 120.146946,
      latitude: 30.188173, source_url: 'https://www.amap.com/search?query=test' }
  } };
  const html = render(React.createElement(PositionPanel, props));
  assert.match(html, /高德地址：江南大道/); assert.match(html, />高德查看 ↗<\/a>/);
  assert.doesNotMatch(html, /茂御居|<details|POI ID|GCJ02|120.146946|最近查询|定位状态：/);
  const other = render(React.createElement(PositionPanel, { ...props, communityName: '其他小区' }));
  assert.match(other, /高德名称：茂御居/);
  const unsafe = render(React.createElement(PositionPanel, { ...props, position: {
    ...props.position, selected: { name: '茂御居', geographic_address: '江南大道1号', source_url: 'javascript:alert(1)' }
  } }));
  assert.match(unsafe, /高德地址：江南大道1号/); assert.doesNotMatch(unsafe, /<a /);
});
