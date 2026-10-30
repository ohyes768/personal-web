/* eslint-disable @typescript-eslint/no-require-imports -- Node runner uses a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, filename);
const AppTabs = require('../src/components/AppTabs.tsx').default;

test('review and maintenance sit beside the map view as top-level tabs', () => {
  const html = renderToStaticMarkup(React.createElement(AppTabs, { active: 'map', onChange() {} }));
  assert.equal((html.match(/class="tab-btn/g) || []).length, 6);
  for (const label of ['地图查看', '数据看板', '市场行情', '法拍数据', '小区收录审核', '小区数据维护']) {
    assert.match(html, new RegExp(`>${label}</button>`));
  }
  // 原来的"小区数据管理"总页签已被两个独立页签取代。
  assert.doesNotMatch(html, /小区数据管理/);
  assert.match(html, /class="tab-btn active">地图查看/);
});

test('each top-level tab reports its own key when clicked', () => {
  const clicks = [];
  const tree = AppTabs({ active: 'map', onChange: tab => clicks.push(tab) });
  for (const button of tree.props.children) button.props.onClick();
  assert.deepEqual(clicks, ['map', 'dashboard', 'market', 'auction', 'review', 'maintenance']);
  const active = renderToStaticMarkup(React.createElement(AppTabs, { active: 'maintenance', onChange() {} }));
  assert.match(active, /class="tab-btn active">小区数据维护/);
  assert.match(active, /class="tab-btn ">小区收录审核/);
});
