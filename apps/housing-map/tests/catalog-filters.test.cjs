/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { CatalogClassificationFilter, CatalogTable } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

test('catalog classification filters show mode-specific options and preserve selection', () => {
  const render = (mode, value) => renderToStaticMarkup(React.createElement(CatalogClassificationFilter,
    { mode, value, propertyTypes: ['住宅', '商铺'], onChange() {} }));
  assert.match(render('admitted', 'new_house'), /value="new_house" selected="">新房/);
  assert.match(render('admitted', ''), />全部<.*>新房<.*>二手房</);
  const excluded = render('excluded', '住宅');
  assert.match(excluded, />全部用途</);
  for (const label of ['住宅', '其他', '写字楼', '商铺', '用途资料缺失']) assert.ok(excluded.includes(label));
  assert.equal((excluded.match(/>住宅</g) || []).length, 1);
  assert.equal(render('auctions', ''), '');
});

test('excluded table displays the same TMSF types used by server filtering', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '办公楼', property_types: ['写字楼'], market_state: 'new_house', sources: [], facts_state: 'complete', exclusion_reason: '用途不符' }] }));
  assert.match(html, /写字楼/);
  assert.match(html, /<th>房屋用途<\/th>/);
  assert.match(html, /data-label="房屋用途">写字楼<\/td>/);
  assert.doesNotMatch(html, /新房项目|用途 \/ 市场/);
  assert.doesNotMatch(html, /用途资料缺失/);
});

test('admitted table shows new or second-hand classification without repeating property use', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [
      { community_id: '1', community_name: '测试一', property_types: ['住宅'], market_state: 'new_house' },
      { community_id: '2', community_name: '测试二', property_types: ['住宅'], market_state: 'second_hand' },
      { community_id: '3', community_name: '测试三', property_types: ['住宅'], market_state: 'unknown' },
    ] }));
  assert.match(html, /<th>新房 \/ 二手房<\/th>/);
  assert.match(html, /data-label="新房 \/ 二手房">新房项目<\/td>/);
  assert.match(html, /data-label="新房 \/ 二手房">二手房<\/td>/);
  assert.match(html, /新房 \/ 二手房状态未知/);
  assert.doesNotMatch(html, /住宅|用途 \/ 市场/);
});
