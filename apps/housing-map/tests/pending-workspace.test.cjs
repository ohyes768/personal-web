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
const { PendingTable, default: PendingWorkspace } = require('../src/components/community/PendingWorkspace.tsx');

test('one identity exposes each independent action without duplicate rows', () => {
  const issues = [{ kind: 'admission', reason: 'position_pending', operation: 'position', label: '待定位' },
    { kind: 'rental', reason: 'search_failed', label: '租金来源查找失败', rental: { community_id: 'c' } }];
  const row = { key: 'community:c', community_id: 'c', name: '<花园>', address: '某路', district: '滨江', issues };
  const calls = [];
  const tree = PendingTable({ items: [row], onProcess: (...args) => calls.push(args) });
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'button') node.props.onClick();
    visit(node.props?.children);
  }
  visit(tree);
  assert.deepEqual(calls, [[row, issues[0]], [row, issues[1]]]);
  const html = renderToStaticMarkup(tree);
  assert.equal((html.match(/<tr>/g) || []).length, 2);
  assert.match(html, /&lt;花园&gt;/);
  assert.match(html, /地点待处理/); assert.match(html, /重试查找/);
  assert.match(html, /data-label="操作"/);
});

test('auction deep entry opens unified queue with dropdowns instead of nested tabs', () => {
  const html = renderToStaticMarkup(React.createElement(PendingWorkspace, {
    initialKind: 'auction', revision: 0, active: true, busy: false,
    onSelect() {}, onAuction() {}, onChanged() {}, onCount() {}, onSyncAuctions() {},
  }));
  assert.match(html, /value="auction" selected=""/);
  assert.match(html, /同步历史法拍/); assert.match(html, /包含已跳过/);
  assert.match(html, /未查询的租金来源/);
  assert.doesNotMatch(html, /review-tabs|tablist/);
});
