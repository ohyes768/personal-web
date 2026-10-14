/* eslint-disable @typescript-eslint/no-require-imports -- CommonJS Node test runner and local TS transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);

test('residential table explains confirmation and missing coordinates', () => {
  const { CommunityTable } = require('../src/components/community/CommunityWorkspace.tsx');
  const html = renderToStaticMarkup(React.createElement(CommunityTable, { items: [{
    community_id: 'local-1', community_name: '住宅花园', aliases: ['花园'], district: '滨江',
    admission: { decision_kind: 'manual' }, effective_property_type: '住宅', map_status: 'missing_coordinates', sources: [],
  }], onSelect() {} }));
  assert.match(html, /名称.*别名/); assert.match(html, /物业类型.*确认方式/);
  assert.match(html, /人工确认/); assert.match(html, /缺坐标/); assert.match(html, /住宅花园/);
});

test('review table counts communities with separate asset and round clues', () => {
  const { ReviewTable } = require('../src/components/community/CommunityWorkspace.tsx');
  const html = renderToStaticMarkup(React.createElement(ReviewTable, { items: [{
    id: 'review-1', name: '测试花园', members: [], sources: ['laipai'], reasons: ['用途待核实'],
    suggestions: [], auction_assets: 2, auction_rounds: 3, auction_identity_uncertain: true,
  }], onSelect() {} }));
  assert.match(html, /候选小区/); assert.match(html, /待审核原因/);
  assert.match(html, /2.*已知资产.*3.*轮次/); assert.match(html, /资产编号缺失/);
  assert.match(html, /用途待核实/); assert.match(html, /审核/);
});

test('management has separate residential, review and excluded tabs', () => {
  const Management = require('../src/components/community/CommunityManagement.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Management, { onChanged() {} }));
  assert.match(html, /住宅小区/); assert.match(html, /待审核小区/); assert.match(html, /不收录/);
  assert.doesNotMatch(html, /审核状态/);
  assert.doesNotMatch(html, /统一小区|来源名称 \/ 待关联/);
  assert.match(html, /最近一次来源采集/); assert.match(html, /小区库存/);
});

test('auction review entry sends users to the shared community workspace', () => {
  const Entry = require('../src/components/auction/AuctionPendingAssociations.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Entry, { refreshVersion: 0, onChanged() {} }));
  assert.match(html, /前往待审核小区/); assert.match(html, /来拍/);
  assert.doesNotMatch(html, /确认绑定|搜索目标小区/);
});


test('excluded records have selectable rows for batch removal', () => {
  const { ReviewTable } = require('../src/components/community/CommunityWorkspace.tsx');
  const html = renderToStaticMarkup(React.createElement(ReviewTable, { items: [{
    id: 'review-noaddr', name: '襄七房', state: 'excluded', members: [], sources: ['tmsf'],
    reasons: ['缺少有效地址，不收录'], suggestions: [], auction_assets: 0, auction_rounds: 0,
  }], onSelect() {}, removal: ['review-noaddr'], onToggle() {} }));
  assert.match(html, /type="checkbox"/); assert.match(html, /checked=""/);
  assert.match(html, /选择移除襄七房/); assert.match(html, /查看原因/);
  assert.match(html, /缺少有效地址/);
});

test('newhouse is independent of use and missing map coordinates', () => {
  const { CommunityTable } = require('../src/components/community/CommunityWorkspace.tsx');
  const html = renderToStaticMarkup(React.createElement(CommunityTable, { items: [{
    community_id: 'local-new', community_name: '新房住宅', district: '滨江',
    admission: { decision_kind: 'manual' }, effective_property_type: '住宅',
    market_state: 'new_house', map_status: 'missing_coordinates', sources: [],
  }], onSelect() {} }));
  assert.match(html, /新房项目/); assert.match(html, /住宅/); assert.match(html, /缺坐标/);
  const { DirectorySourceCard } = require('../src/components/community/DirectoryCards.tsx');
  const source = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_id: '1', source_kind: 'community', name: '新房住宅',
    status: 'matched', market_state: 'new_house', project_sale_status: '售完',
    property_type: '住宅', residential_state: 'residential', property_type_error: '请求失败',
  } }));
  assert.match(source, /售完/); assert.match(source, /保留上次有效用途证据/); assert.match(source, /✅ 住宅/);
});

test('source detail identifies project and coordinate evidence separately', () => {
  const { DirectorySourceCard, AdmissionControls } = require('../src/components/community/DirectoryCards.tsx');
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_kind: 'community', source_id: '3017629894', name: '新房住宅',
    status: 'matched', project_id: '2313460053', project_name: '朗拾滨屿府', market_state: 'new_house',
    market_state_captured_at: '2026-10-14T00:00:00Z',
    coordinate_evidence: { source: 'historical_amap', source_id: '3017629894' },
  }}));
  assert.match(html, /3017629894/); assert.match(html, /2313460053/);
  assert.match(html, /项目身份核验时间/); assert.match(html, /历史高德地理编码/);
  const admission = renderToStaticMarkup(React.createElement(AdmissionControls, { community: {
    community_id: 'c', community_name: '新房住宅', admission_state: 'admitted', map_status: 'displayed',
    admission: { state: 'admitted', revision: 1, decision_kind: 'automatic' },
  }, busy: false, onDecision() {} }));
  assert.match(admission, /自动收录/); assert.doesNotMatch(admission, /尚未审核/);
});
