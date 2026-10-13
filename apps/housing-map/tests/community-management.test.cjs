/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { DirectorySourceCard, ResidentialStateBadge, safeDirectoryLink } = require('../src/components/community/CommunityManagement.tsx');
test('source card preserves original identity, manual method and evidence', () => {
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 'r', source: 'fang', source_kind: 'community', source_id: '123', name: '花园一期',
    status: 'matched', method: 'manual', address: '测试路', evidence: ['完整名称一致'], source_url: 'https://zu.fang.com/hz/house-xm123/',
  }}));
  assert.match(html, /花园一期/); assert.match(html, /123/); assert.match(html, /人工关联/); assert.match(html, /完整名称一致/);
  assert.match(html, /noopener noreferrer/);
});
test('directory links reject executable schemes and credentials', () => {
  assert.equal(safeDirectoryLink('javascript:alert(1)'), undefined);
  assert.equal(safeDirectoryLink('https://user:password@example.com'), undefined);
  assert.equal(safeDirectoryLink('https://www.amap.com/'), 'https://www.amap.com/');
});
test('property evidence shows retained type, pending failure and source link', () => {
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_kind: 'community', source_id: '1', name: '测试花园', status: 'pending',
    residential_state: 'pending', property_type: '住宅', property_type_error: '本次获取失败',
    property_type_captured_at: '2026-10-13T00:00:00+00:00',
    property_type_url: 'https://www.tmsf.com/esf/xq_indexnew_1.htm',
  }}));
  assert.match(html, /物业类型：住宅/);
  assert.match(html, /待核实/);
  assert.match(html, /本次获取失败/);
  assert.match(html, /2026-10-13/);
  assert.match(html, /查看物业类型来源/);
  const unsafe = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_kind: 'community', source_id: '1', name: '花园', status: 'pending',
    property_type_url: 'javascript:alert(1)',
  }}));
  assert.doesNotMatch(unsafe, /查看物业类型来源/);
});
test('residential badge shows ✅ for residential, ❓ for pending, ❌ for non_residential', () => {
  const cases = [
    ['residential', /✅ 住宅/, 'directory-residential'],
    ['pending', /❓ 待核实/, 'directory-pending'],
    ['non_residential', /❌ 非住宅/, 'directory-non-residential'],
  ];
  for (const [state, contentRe, klass] of cases) {
    const html = renderToStaticMarkup(React.createElement(ResidentialStateBadge, { state }));
    assert.match(html, contentRe);
    assert.match(html, new RegExp(klass));
  }
  const empty = renderToStaticMarkup(React.createElement(ResidentialStateBadge, { state: undefined }));
  assert.match(empty, /—/);
});
test('amap source shows geographic classification as a hint, not property use', () => {
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 'a1', source: 'amap', source_kind: 'poi', source_id: 'B1', name: '测试花园西区', status: 'pending',
    residential_state: 'pending', poi_type: '商务住宅;住宅区;住宅小区', residential_hint: true,
    source_url: 'https://www.amap.com/search?query=test',
  }}));
  assert.match(html, /高德地图/); assert.match(html, /住宅小区/);
  assert.match(html, /仅作住宅线索/); assert.match(html, /待核实/); assert.match(html, /测试花园西区/);
});
test('directory collection defaults to tmsf and amap only', () => {
  const Management = require('../src/components/community/CommunityManagement.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Management, { onChanged() {} }));
  const controls = html.slice(html.indexOf('directory-collection'), html.indexOf('directory-toolbar'));
  assert.equal((controls.match(/type="checkbox"/g) || []).length, 2);
  assert.match(controls, /透明售房网/); assert.match(controls, /高德地图/);
  assert.doesNotMatch(controls, /房天下|来拍/); assert.match(controls, /失败或截断不代表采全/);
});
