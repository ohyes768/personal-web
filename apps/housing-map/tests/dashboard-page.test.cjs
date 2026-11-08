/* eslint-disable @typescript-eslint/no-require-imports -- Node runner uses a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const path = require('node:path');
const Module = require('node:module');
// '@/x' 是 Next 的路径别名, node 直跑时要自己映射回 src/
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...args) {
  if (request.startsWith('@/')) request = path.join(__dirname, '..', 'src', request.slice(2));
  return originalResolve.call(this, request, ...args);
};
const { DashboardPage } = require('../src/app/page.tsx');

function makeCommunity(id, overrides = {}) {
  return {
    community_id: id,
    community_name: `小区${id}`,
    district: '滨江',
    subdistrict: '浦沿',
    address: '测试地址',
    latitude: 30.2,
    longitude: 120.2,
    market_state: 'second_hand',
    price: {
      listing_avg_price: 40000,
      deal_avg_price: 38000,
      snapshot_date: '2026-11-01',
      counts: { deal_count: 3, listing_count: 10 },
    },
    pois: [],
    score: { total_score: 80, location_score: 70, amenity_score: 75, product_score: 72, market_score: 68 },
    ...overrides,
  };
}

const communities = [
  makeCommunity('二手甲'),
  makeCommunity('二手乙', { market_state: 'second_hand', price: { listing_avg_price: null, deal_avg_price: null, snapshot_date: '2026-11-01', counts: { deal_count: 0 } } }),
  makeCommunity('新房丙', { market_state: 'new_house', price: {}, score: {} }),
  makeCommunity('待核实丁', { market_state: 'unknown' }),
];

function render(props = {}) {
  return renderToStaticMarkup(React.createElement(DashboardPage, {
    communities,
    onView() {},
    searchQuery: '',
    page: 1, setPage() {},
    subdistrictFilter: '', setSubdistrictFilter() {},
    priceFilter: '', setPriceFilter() {},
    scoreFilter: '', setScoreFilter() {},
    marketFilter: 'all', setMarketFilter() {},
    sortKey: 'total_score', setSortKey() {},
    sortOrder: 'desc', setSortOrder() {},
    ...props,
  }));
}

test('the dashboard offers a housing-type filter with all four buckets', () => {
  const html = render();
  assert.match(html, /aria-label="房源类型筛选"/);
  for (const label of ['全部房源', '二手房', '新房项目', '房源类型待核实']) {
    assert.match(html, new RegExp(`<option[^>]*>${label}</option>`));
  }
});

test('the statistics split second-hand, new houses and unverified entries', () => {
  const html = render();
  // 4 个小区 = 2 二手 + 1 新房 + 1 待核实
  assert.match(html, /<div class="stat-value">4<\/div><div class="stat-label">小区总数 \(当前筛选\)<\/div>/);
  assert.match(html, /<div class="stat-value">2<\/div><div class="stat-label">其中二手房<\/div>/);
  assert.match(html, /<div class="stat-value">1<\/div><div class="stat-label">其中新房项目<\/div>/);
  // 均价只对有价的二手房取平均 (38000), 无价二手房不按 0 拉低
  assert.match(html, /<div class="stat-value">38,000<\/div><div class="stat-label">二手房均价 \(元\/㎡\)<\/div>/);
  assert.match(html, /<div class="stat-value">3<\/div><div class="stat-label">二手房近30日签约 \(套\)<\/div>/);
  assert.match(html, /<div class="stat-value">1<\/div><div class="stat-label">二手房有价小区<\/div>/);
});

test('choosing new houses leaves only new-house rows and blanks the second-hand metrics', () => {
  const html = render({ marketFilter: 'new_house' });
  assert.match(html, /小区新房丙/);
  assert.doesNotMatch(html, /小区二手甲/);
  assert.doesNotMatch(html, /小区待核实丁/);
  // 二手专属指标显示「—」, 不显示 0
  assert.match(html, /<div class="stat-value">—<\/div><div class="stat-label">二手房均价 \(元\/㎡\)<\/div>/);
  assert.match(html, /<div class="stat-value">—<\/div><div class="stat-label">二手房近30日签约 \(套\)<\/div>/);
});

test('choosing second-hand keeps only second-hand rows', () => {
  const html = render({ marketFilter: 'second_hand' });
  assert.match(html, /小区二手甲/);
  assert.match(html, /小区二手乙/);
  assert.doesNotMatch(html, /小区新房丙/);
  assert.doesNotMatch(html, /小区待核实丁/);
});
