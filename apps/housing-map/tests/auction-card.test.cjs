/* eslint-disable @typescript-eslint/no-require-imports -- Node tests use a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, filename);
test('card shows latest sale instead of median and has no navigation', () => {
  const { LatestAuctionCardContent } = require('../src/components/community/LatestAuctionCard.tsx');
  const html = renderToStaticMarkup(React.createElement(LatestAuctionCardContent, { data: {
    available: true, records: [{ deal_unit_price: 31882, area_m2: 149.3, end_at: '2026-09-29T10:37:33+08:00' }],
    stats: { median_unit_price_yuan: 40000 }
  } }));
  assert.match(html, /最近法拍成交/);
  assert.match(html, /3.19万/);
  assert.match(html, /2026\/9\/29/);
  assert.match(html, /149.3㎡/);
  assert.doesNotMatch(html, /4.00万|<a|<button/);
});
test('missing latest area does not silently substitute an older price', () => {
  const { LatestAuctionCardContent } = require('../src/components/community/LatestAuctionCard.tsx');
  const render = data => renderToStaticMarkup(React.createElement(LatestAuctionCardContent, { data }));
  assert.match(render({ available: true, records: [{ deal_unit_price: null, area_m2: null, end_at: '2026-09-29' }] }), /面积未知/);
  assert.match(render({ available: true, records: [] }), /暂无成交/);
  assert.match(render({ available: false, records: [] }), /尚未采集/);
});
