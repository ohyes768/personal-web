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
const { CatalogClassificationFilter, CatalogTable, CatalogTabs, catalogScope } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

test('pipeline tabs split pending from final exclusions with distinct counts and queries', () => {
  const summary = { active: true, pipeline: true, admitted: 89, pending: 254, excluded: 355, auction_pending: 32 };
  const html = renderToStaticMarkup(React.createElement(CatalogTabs, { summary, mode: 'pending', onChange() {} }));
  assert.match(html, /aria-pressed="true">待处理（254）/);
  assert.match(html, />不收录（101）/);
  assert.match(html, />已收录（89）/);
  assert.doesNotMatch(html, /待处理 \/ 不收录|收录处理状态/);
  assert.deepEqual(catalogScope('pending', true), { state: 'excluded', workflow: 'pending' });
  assert.deepEqual(catalogScope('excluded', true), { state: 'excluded', workflow: 'excluded' });
  assert.deepEqual(catalogScope('admitted', true), { state: 'admitted', workflow: '' });
  const clicks = [];
  const tabs = CatalogTabs({ summary, mode: 'pending', onChange: mode => clicks.push(mode) });
  tabs.props.children.find(button => button.key === 'excluded').props.onClick();
  tabs.props.children.find(button => button.key === 'pending').props.onClick();
  assert.deepEqual(clicks, ['excluded', 'pending']);
  const legacy = renderToStaticMarkup(React.createElement(CatalogTabs, { summary: { ...summary, pipeline: false }, mode: 'excluded', onChange() {} }));
  assert.doesNotMatch(legacy, /待处理/);
  assert.match(legacy, /不收录（355）/);
  assert.deepEqual(catalogScope('excluded', false), { state: 'excluded', workflow: '' });
});

test('pending catalog labels unfinished reasons without calling them exclusions', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, pending: true, busy: false, select() {}, retry() {},
    items: [{ community_id: 'p', community_name: '待确认小区', exclusion_reason: '请确认主体地点', facts_state: 'complete' }] }));
  assert.match(html, /<th>待处理原因 \/ 资料状态<\/th>/);
  assert.match(html, /待核对/);
  assert.doesNotMatch(html, /不收录原因|条件不符/);
});

test('pending rows offer direct exclusion in a dedicated column and preserve row identity', () => {
  const row = { community_id: 'road', community_name: '东信大道', qualification: 'position_review', admission: { revision: 3 } };
  const calls = [];
  const props = { items: [row], excluded: true, pending: true, busy: false, select() {}, retry() {}, exclude: r => calls.push(r) };
  const html = renderToStaticMarkup(React.createElement(CatalogTable, props));
  assert.match(html, /<th>收录决定<\/th>/);
  assert.match(html, /data-label="收录决定"><button[^>]*>确认不收录<\/button>/);
  assert.doesNotMatch(html, /请选择不收录原因|具体原因/);
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'td' && node.props['data-label'] === '收录决定') node.props.children.props.onClick();
    else visit(node.props?.children);
  }
  visit(CatalogTable(props));
  assert.deepEqual(calls, [row]);
  const busy = renderToStaticMarkup(React.createElement(CatalogTable, { ...props, busy: true }));
  assert.match(busy, /disabled=""[^>]*>确认不收录/);
  const virtual = renderToStaticMarkup(React.createElement(CatalogTable, { ...props, items: [{ ...row, source_record_id: 'source-only' }] }));
  assert.doesNotMatch(virtual, />确认不收录</);
  assert.match(virtual, /需先补齐身份/);
});

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
