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

test('compact TMSF source shows evidence and collection metadata without expanding', () => {
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { compact: true, item: {
    id: 't1', source: 'tmsf', source_kind: 'community', source_id: '170413978', name: '世茂之西湖',
    method: 'manual', status: 'matched', address: '滨江区一桥南侧', district: '滨江', property_type: '住宅', market_state: 'second_hand',
    property_type_captured_at: '2026-10-16T07:57:26.217682+00:00',
    property_type_url: 'https://www.tmsf.com/esf/xq_indexnew_170413978.htm',
    source_url: 'https://www.tmsf.com/include/hzweb/index_search_newCommunitylist.js'
  } }));
  assert.match(html, /住宅 · 二手房/);
  assert.match(html, /href="https:\/\/www.tmsf.com\/esf\/xq_indexnew_170413978.htm"[^>]*>查看来源/);
  assert.doesNotMatch(html, /index_search_newCommunitylist|打开原始来源|物业类型：|—/);
  assert.doesNotMatch(html, /<details|<summary|采集详情/);
  assert.match(html, /人工关联/); assert.match(html, /来源 ID：170413978/);
  assert.match(html, /来源地址：滨江区一桥南侧/);
  assert.match(html, /15:57:26（北京时间）/);
});

test('compact source never falls back to a TMSF script and rental source omits unrelated unknowns', () => {
  const render = item => renderToStaticMarkup(React.createElement(DirectorySourceCard, { compact: true, item: {
    id: 's', source_kind: 'community', source_id: '1', name: '测试小区', status: 'matched', ...item
  } }));
  assert.doesNotMatch(render({ source: 'tmsf', source_url: 'https://www.tmsf.com/list.js?x=1' }), /<a\s|list\.js/);
  const rental = render({ source: 'fang', market_state: 'unknown', source_url: 'https://zu.fang.com/hz/house-xm1/' });
  assert.match(rental, /租金来源/); assert.match(rental, /查看来源/);
  assert.doesNotMatch(rental, /物业类型|尚未获取|新房 \/ 二手房状态未知/);
});

test('admission controls distinguish reversible review/exclusion from whole deletion', () => {
  const { AdmissionControls } = require('../src/components/community/CommunityManagement.tsx');
  const render = state => renderToStaticMarkup(React.createElement(AdmissionControls, {
    community: { community_id: '100', community_name: '江汉路小区', admission_state: state,
      admission: { state, revision: 2, decision_kind: 'manual', auto_review_locked: true, reason: '疑似道路' },
      map_status: 'not_admitted' }, busy: false, onDecision() {} }));
  assert.match(render('admitted'), /移到待审核/);
  assert.match(render('admitted'), /排除收录/);
  assert.match(render('pending'), /确认收录/);
  assert.match(render('pending'), /自动审核已锁定/);
  assert.match(render('pending'), /疑似道路/);
  assert.match(render('excluded'), /恢复到待审核/);
  assert.doesNotMatch(render('excluded'), /确认收录/);
  assert.doesNotMatch(render('admitted'), /删除整个/);
});
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
test('management offers independent collection tasks without a discovery source selector', () => {
  const Management = require('../src/components/community/CommunityManagement.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Management, { onChanged() {} }));
  assert.match(html, /采集任务/);
  assert.doesNotMatch(html, /采集来源|数据来源|自动审核启用|待审核小区/);
});
