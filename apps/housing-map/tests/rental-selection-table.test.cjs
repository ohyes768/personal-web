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
const { RentalSelectionTable } = require('../src/components/rental/RentalAssociationReview.tsx');

test('pending selection shows four useful columns and opens the existing review by identity', () => {
  const calls = [];
  const tree = RentalSelectionTable({ items: [{ community_id: 'c1', community_name: '风景蝶院', address: '测试路',
    candidates: [{ name: '留园' }, { name: '观园' }, { name: '其他园' }], candidate_count: 3, selectable_count: 2,
    selection_reason: '候选范围不同，请核对后选择对应分园' }], onReview: id => calls.push(id) });
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'button') node.props.onClick();
    visit(node.props?.children);
  }
  visit(tree);
  assert.deepEqual(calls, ['c1']);
  const html = renderToStaticMarkup(tree);
  for (const title of ['小区', '候选情况', '待确认原因', '操作']) assert.match(html, new RegExp(`<th>${title}</th>`));
  assert.match(html, /2 个可人工选择/);
  assert.match(html, /留园、观园等，共 3 个/);
  assert.doesNotMatch(html, /其他园|最近处理|相似度/);
  assert.match(html, /核对候选/);
  assert.match(html, /data-label="候选情况"/);
});

test('all blocked and old empty summaries remain inspectable without claiming selectable candidates', () => {
  const html = renderToStaticMarkup(React.createElement(RentalSelectionTable, { items: [
    { community_id: 'x', community_name: '<锦绣江南>', candidates: [{ name: '桐庐锦绣江南' }],
      candidate_count: 1, selectable_count: 0, selection_reason: '候选位于桐庐，与滨江不一致' },
    { community_id: 'legacy', community_name: '旧记录', candidates: [] },
  ], onReview() {} }));
  assert.match(html, /0 个可人工选择/);
  assert.match(html, /候选位于桐庐/);
  assert.match(html, /候选资料待刷新/);
  assert.match(html, /&lt;锦绣江南&gt;/);
  assert.doesNotMatch(html, /disabled/);
});
