/* eslint-disable @typescript-eslint/no-require-imports -- Node runner uses a local TypeScript transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const {
  DASH_MARKET_FILTER_OPTIONS,
  matchesDashMarket,
  filterDashboardCommunities,
  dashboardStats,
} = require('../src/lib/dashboard-filter.ts');

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
    score: { total_score: 80, location_score: null, amenity_score: null, product_score: null, market_score: null },
    ...overrides,
  };
}

const secondHand = makeCommunity('二手', { market_state: 'second_hand' });
const newHouse = makeCommunity('新房', { market_state: 'new_house', price: {}, score: {} });
const unknown = makeCommunity('待核实', { market_state: 'unknown' });
const missingState = makeCommunity('无字段', { market_state: undefined });

function ids(list) {
  return list.map(c => c.community_id).sort();
}

function filterWith(list, overrides = {}) {
  return filterDashboardCommunities(list, {
    searchQuery: '', subdistrict: '', priceRange: '', scoreRange: '', market: 'all', ...overrides,
  });
}

test('the market filter splits second-hand, new houses and unverified entries apart', () => {
  assert.deepEqual(DASH_MARKET_FILTER_OPTIONS.map(o => o.value), ['all', 'second_hand', 'new_house', 'unknown']);
  assert.deepEqual(DASH_MARKET_FILTER_OPTIONS.map(o => o.label), ['全部房源', '二手房', '新房项目', '房源类型待核实']);

  const all = [secondHand, newHouse, unknown, missingState];
  assert.deepEqual(ids(filterWith(all)), ['二手', '待核实', '无字段', '新房'].sort());
  assert.deepEqual(ids(filterWith(all, { market: 'second_hand' })), ['二手']);
  assert.deepEqual(ids(filterWith(all, { market: 'new_house' })), ['新房']);
  // 待核实(含缺失字段)不是二手房, 只在它自己的档里出现
  assert.deepEqual(ids(filterWith(all, { market: 'unknown' })), ['待核实', '无字段'].sort());
});

test('matchesDashMarket never treats an unverified entry as second-hand', () => {
  assert.equal(matchesDashMarket(secondHand, 'second_hand'), true);
  assert.equal(matchesDashMarket(missingState, 'second_hand'), false);
  assert.equal(matchesDashMarket(missingState, 'new_house'), false);
  assert.equal(matchesDashMarket(missingState, 'all'), true);
});

test('the four price bands form a complete and mutually exclusive partition', () => {
  const cheap = makeCommunity('便宜', { price: { listing_avg_price: 18000, deal_avg_price: null, snapshot_date: '2026-11-01' } });
  const mid = makeCommunity('中等', { price: { listing_avg_price: 30000, deal_avg_price: null, snapshot_date: '2026-11-01' } });
  const upper = makeCommunity('中高', { price: { listing_avg_price: 40000, deal_avg_price: null, snapshot_date: '2026-11-01' } });
  const pricey = makeCommunity('贵', { price: { listing_avg_price: 60000, deal_avg_price: null, snapshot_date: '2026-11-01' } });
  const noPrice = makeCommunity('无价', { price: { listing_avg_price: null, deal_avg_price: null, snapshot_date: '2026-11-01' } });
  const list = [cheap, mid, upper, pricey, noPrice];

  // "2万以下" 必须只收有价且低于 2 万的, 不能再把 2 万以上一起留下
  assert.deepEqual(ids(filterWith(list, { priceRange: '0-20000' })), ['便宜']);
  assert.deepEqual(ids(filterWith(list, { priceRange: '20000-35000' })), ['中等']);
  assert.deepEqual(ids(filterWith(list, { priceRange: '35000-50000' })), ['中高']);
  assert.deepEqual(ids(filterWith(list, { priceRange: '50000-999999' })), ['贵']);
  // 无价小区不落入任何价格档
  for (const range of ['0-20000', '20000-35000', '35000-50000', '50000-999999']) {
    assert.equal(ids(filterWith(list, { priceRange: range })).includes('无价'), false);
  }
  // 新房没有价格, 选择价格区间后不参与匹配
  assert.deepEqual(ids(filterWith([...list, newHouse], { priceRange: '0-20000', market: 'new_house' })), []);
});

test('the statistics keep second-hand metrics away from new houses and unverified entries', () => {
  const stats = dashboardStats([secondHand, newHouse, unknown]);
  assert.equal(stats.total, 3);
  assert.equal(stats.secondHand, 1);
  assert.equal(stats.newHouse, 1);
  assert.equal(stats.unknown, 1);
  assert.equal(stats.avgPrice, 38000);   // 签约价优先
  assert.equal(stats.dealCount, 3);
  assert.equal(stats.withPrice, 1);
});

test('the average price only averages the priced second-hand entries', () => {
  const priced = makeCommunity('有价', { price: { listing_avg_price: null, deal_avg_price: 30000, snapshot_date: '2026-11-01', counts: { deal_count: 2 } } });
  const priceless = makeCommunity('无价', { price: { listing_avg_price: null, deal_avg_price: null, snapshot_date: '2026-11-01', counts: { deal_count: 0 } } });
  const stats = dashboardStats([priced, priceless]);
  // 无价小区不按 0 参与平均, 否则把均价拉低
  assert.equal(stats.avgPrice, 30000);
  assert.equal(stats.withPrice, 1);
  assert.equal(stats.dealCount, 2);
});
