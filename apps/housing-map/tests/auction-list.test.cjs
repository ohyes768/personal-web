/* eslint-disable @typescript-eslint/no-require-imports -- Local TypeScript transform for Node tests. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, filename);
test('list preserves unmatched rounds and hides non-deal prices and unsafe links', () => {
  const { AuctionListContent } = require('../src/components/auction/AuctionDataList.tsx');
  const html = renderToStaticMarkup(React.createElement(AuctionListContent, { onView: () => {}, data: {
    available: true, overall_total: 4, total: 2, records: [
      { source: 'laipai', auction_id: '1', title: '<住宅>', status: 'todo', area_m2: null, deal_price_yuan: 9999999, original_url: 'javascript:alert(1)', risk_notes: { rent_desc: '<script>风险</script>' } },
      { source: 'laipai', auction_id: '2', title: '已成交', status: 'done', area_m2: 149.3, deal_price_yuan: 4760000, deal_unit_price: 31882, community_id: 'c', community_display_name: '花园' }
    ]
  }}));
  assert.match(html, /累计 4 条拍卖记录/);
  assert.match(html, /未关联小区/);
  assert.match(html, /面积未知/);
  assert.match(html, /476.00万/);
  assert.match(html, /31,882/);
  assert.match(html, /地图查看/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /999.99|javascript:/);
});
test('uncollected and filtered empty states differ', () => {
  const { AuctionListContent } = require('../src/components/auction/AuctionDataList.tsx');
  const render = data => renderToStaticMarkup(React.createElement(AuctionListContent, { data, onView: () => {} }));
  assert.match(render({ available: false }), /尚未采集/);
  assert.match(render({ available: true, overall_total: 4, total: 0, records: [] }), /当前筛选无结果/);
  assert.match(render({ available: true, overall_total: 0, total: 0, records: [] }), /暂无法拍记录/);
});
