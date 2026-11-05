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

test('review and maintenance are separate entries into the community workspace', () => {
  const Management = require('../src/components/community/CommunityManagement.tsx').default;
  // 收录审核入口只看住宅名单的收录状态，不掺法拍待关联。
  const review = renderToStaticMarkup(React.createElement(Management, { onChanged() {}, initialMode: 'admitted' }));
  assert.match(review, /已收录/); assert.match(review, /不收录/);
  assert.doesNotMatch(review, /法拍待关联/);
  assert.doesNotMatch(review, /待审核小区|先预演|启用自动审核/);
  // 小区数据维护入口走自己的两个页签，不再复用收录状态页签。
  const maintenance = renderToStaticMarkup(React.createElement(Management, { onChanged() {}, initialMode: 'rental' }));
  assert.match(maintenance, /aria-label="维护事项"/);
  assert.match(maintenance, /aria-pressed="true">租金来源/);
  assert.match(maintenance, />法拍待关联（…）</);
  assert.doesNotMatch(maintenance, /已收录/);
});

test('auction review entry sends users to the shared community workspace', () => {
  const Entry = require('../src/components/auction/AuctionPendingAssociations.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Entry, { refreshVersion: 0, onChanged() {} }));
  assert.match(html, /前往待审核小区/); assert.match(html, /来拍/);
  assert.doesNotMatch(html, /确认绑定|搜索目标小区/);
});

test('new house source keeps market evidence and retained type errors', () => {
  const { DirectorySourceCard } = require('../src/components/community/DirectoryCards.tsx');
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_id: '1', source_kind: 'community', name: '新房住宅',
    status: 'matched', market_state: 'new_house', project_sale_status: '售完',
    property_type: '住宅', residential_state: 'residential', property_type_error: '请求失败',
  } }));
  assert.match(html, /售完/); assert.match(html, /保留上次有效用途证据/); assert.match(html, /✅ 住宅/);
});

test('source detail identifies project and coordinate evidence separately', () => {
  const { DirectorySourceCard } = require('../src/components/community/DirectoryCards.tsx');
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 't1', source: 'tmsf', source_kind: 'community', source_id: '3017629894', name: '新房住宅',
    status: 'matched', project_id: '2313460053', project_name: '朗拾滨屿府', market_state: 'new_house',
    market_state_captured_at: '2026-10-14T00:00:00Z',
    coordinate_evidence: { source: 'historical_amap', source_id: '3017629894' },
  } }));
  assert.match(html, /3017629894/); assert.match(html, /2313460053/);
  assert.match(html, /项目身份核验时间/); assert.match(html, /历史高德地理编码/);
});
