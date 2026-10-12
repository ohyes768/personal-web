/* eslint-disable @typescript-eslint/no-require-imports -- Node CommonJS test runner installs a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) {
  require.extensions[ext] = (module, filename) => {
    module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
    }).outputText, filename);
  };
}
test('history shows samples, missing area, escaped facts and safe links', () => {
  const { AuctionHistoryContent } = require('../src/components/community/CommunityAuctionHistory.tsx');
  const html = renderToStaticMarkup(React.createElement(AuctionHistoryContent, { data: {
    available: true, last_run: { complete: false, finished_at: '2026-10-09T10:00:00Z' },
    stats: { deal_property_count: 1, unit_price_sample_count: 0, median_unit_price_yuan: null,
      min_unit_price_yuan: null, max_unit_price_yuan: null, latest_end_at: '2026-09-01', sample_warning: '参考样本较少' },
    records: [{ source: 'laipai', auction_id: '1', title: '房源', area_m2: null, round: 2,
      deal_price_yuan: 4760000, deal_unit_price: null, end_at: '2026-09-01',
      risk_notes: { rent_desc: '<script>bad</script>' }, original_url: 'javascript:alert(1)', rounds: [] }]
  } }));
  assert.match(html, /参考样本较少/);
  assert.match(html, /面积未知/);
  assert.match(html, /476/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /未核验付款或过户/);
});
test('uncollected data differs from empty filtered history', () => {
  const { AuctionHistoryContent } = require('../src/components/community/CommunityAuctionHistory.tsx');
  assert.match(renderToStaticMarkup(React.createElement(AuctionHistoryContent, { data: { available: false } })), /尚未采集/);
  assert.match(renderToStaticMarkup(React.createElement(AuctionHistoryContent, { data: {
    available: true, records: [], stats: { deal_property_count: 0, unit_price_sample_count: 0 }
  } })), /暂无成交记录/);
});
