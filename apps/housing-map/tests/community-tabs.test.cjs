/* eslint-disable @typescript-eslint/no-require-imports -- Node runner uses a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, filename);
test('community navigation keeps the overview without rental or auction tabs', () => {
  const Tabs = require('../src/components/community/CommunityDetailTabs.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Tabs, { communityId: 'c', children: '概况' }));
  assert.doesNotMatch(html, /交易记录/);
  assert.doesNotMatch(html, /法拍成交/);
  assert.doesNotMatch(html, /租金与收益/);
  assert.match(html, /小区概况/);
  assert.match(html, /概况<\/div>/);
});
