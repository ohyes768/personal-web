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
