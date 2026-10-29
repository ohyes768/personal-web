/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const {
  MARKET_MODE_OPTIONS, MARKET_STATE_LABELS, NEARBY_DEFAULT_RADIUS_METERS,
  marketStateOf, isSecondHand, isNewHouse, visibleCommunities,
  haversineMeters, nearbySecondHand, newHousePriceText, secondHandPriceText,
} = require('../src/lib/market-map.ts');

// 沿子午线移动时 haversine 距离恰为 R * Δφ, 用它构造精确的边界测试点
const EARTH_RADIUS_METERS = 6371000;
function metersNorthOf(lat, lng, meters) {
  return { latitude: lat + (meters / EARTH_RADIUS_METERS) * (180 / Math.PI), longitude: lng };
}

function makeCommunity(id, overrides = {}) {
  return {
    community_id: id,
    community_name: `小区${id}`,
    district: '滨江',
    subdistrict: '浦沿',
    address: '测试地址',
    latitude: 30.2,
    longitude: 120.2,
    price: { listing_avg_price: 40659, deal_avg_price: 38500, listing_count: 23, deal_count: 5, snapshot_date: '2026-05-08' },
    pois: [],
    score: { total_score: 78, location_score: null, amenity_score: null, product_score: null, market_score: null },
    ...overrides,
  };
}

test('an absent or invalid market state is unknown and never second-hand', () => {
  assert.equal(marketStateOf(makeCommunity('a')), 'unknown');
  assert.equal(marketStateOf(makeCommunity('a', { market_state: 'new_house' })), 'new_house');
  assert.equal(marketStateOf(makeCommunity('a', { market_state: 'second_hand' })), 'second_hand');
  assert.equal(marketStateOf(makeCommunity('a', { market_state: 'unknown' })), 'unknown');
  assert.equal(marketStateOf(makeCommunity('a', { market_state: 'sold_out' })), 'unknown');
  assert.equal(marketStateOf(makeCommunity('a', { market_state: null })), 'unknown');
  // 未知绝不能被当成二手房混进二手专属聚合
  assert.equal(isSecondHand(makeCommunity('a')), false);
  assert.equal(isNewHouse(makeCommunity('a')), false);
});

test('the three switch options cover every market mode with stable labels', () => {
  assert.deepEqual(MARKET_MODE_OPTIONS, [
    { value: 'second_hand', label: '二手房' },
    { value: 'new_house', label: '新房' },
    { value: 'all', label: '全部' },
  ]);
  assert.equal(MARKET_STATE_LABELS.new_house, '新房项目');
  assert.equal(MARKET_STATE_LABELS.second_hand, '二手房');
  assert.equal(MARKET_STATE_LABELS.unknown, '房源类型待核实');
  assert.equal(NEARBY_DEFAULT_RADIUS_METERS, 1500);
});

test('visible communities keep unknown only in the all mode', () => {
  const communities = [
    makeCommunity('sh1', { market_state: 'second_hand' }),
    makeCommunity('sh2', { market_state: 'second_hand' }),
    makeCommunity('nh1', { market_state: 'new_house' }),
    makeCommunity('uk1'),
  ];
  const secondHand = visibleCommunities(communities, 'second_hand');
  const newHouse = visibleCommunities(communities, 'new_house');
  const all = visibleCommunities(communities, 'all');
  assert.deepEqual(secondHand.map(c => c.community_id), ['sh1', 'sh2']);
  assert.deepEqual(newHouse.map(c => c.community_id), ['nh1']);
  assert.deepEqual(all.map(c => c.community_id), ['sh1', 'sh2', 'nh1', 'uk1']);
  assert.equal(all.length, 4);
  // 未知既不混进二手房也不混进新房
  assert.equal(secondHand.some(c => c.community_id === 'uk1'), false);
  assert.equal(newHouse.some(c => c.community_id === 'uk1'), false);
  // 入参数组不被改动, 返回的是新数组
  const before = communities.map(c => c.community_id);
  visibleCommunities(communities, 'second_hand');
  assert.deepEqual(communities.map(c => c.community_id), before);
  assert.notEqual(visibleCommunities(communities, 'all'), communities);
});

test('the great-circle distance is zero for the same point and metres for a known gap', () => {
  const anchor = { latitude: 30.2, longitude: 120.2 };
  assert.equal(haversineMeters(anchor, anchor), 0);
  const oneKm = metersNorthOf(30.2, 120.2, 1000);
  const distance = haversineMeters(anchor, oneKm);
  assert.ok(distance > 900 && distance < 1100, `1 公里应落在 900~1100 米, 实际 ${distance}`);
  assert.ok(Math.abs(distance - 1000) < 1);
  // 经纬度度数不能直接当距离用
  assert.notEqual(distance, Math.abs(oneKm.latitude - anchor.latitude));
});

test('nearby second-hand listing keeps only second-hand communities inside the radius', () => {
  const anchor = makeCommunity('anchor', { market_state: 'new_house' });
  const at1500 = makeCommunity('at1500', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 1500) });
  const at1501 = makeCommunity('at1501', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 1501) });
  const newHouseNear = makeCommunity('nh', { market_state: 'new_house', ...metersNorthOf(30.2, 120.2, 100) });
  const unknownNear = makeCommunity('uk', { ...metersNorthOf(30.2, 120.2, 100) });

  const nearby = nearbySecondHand(anchor, [at1501, newHouseNear, at1500, unknownNear]);
  // 边界点(正好 1500 米)入选, 1501 米被排除, 新房与未知不参与二手比较
  assert.deepEqual(nearby.map(item => item.community.community_id), ['at1500']);
  assert.equal(nearby[0].distance, 1500);
  assert.equal(typeof nearby[0].distance, 'number');
  assert.ok(Number.isInteger(nearby[0].distance));
});

test('nearby second-hand listing includes price-less communities and excludes the anchor itself', () => {
  const anchor = makeCommunity('anchor', { market_state: 'second_hand' });
  const noPrice = makeCommunity('np', {
    market_state: 'second_hand',
    ...metersNorthOf(30.2, 120.2, 800),
    price: { listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '' },
  });
  const nearby = nearbySecondHand(anchor, [anchor, noPrice]);
  assert.deepEqual(nearby.map(item => item.community.community_id), ['np']);
  assert.equal(nearby[0].distance, 800);
});

test('nearby second-hand listing sorts by distance and breaks ties by community id', () => {
  const anchor = makeCommunity('anchor', { market_state: 'new_house' });
  const far = makeCommunity('far', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 1200) });
  const near = makeCommunity('near', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 300) });
  const tieB = makeCommunity('b-tie', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, -600) });
  const tieA = makeCommunity('a-tie', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 600) });

  const nearby = nearbySecondHand(anchor, [far, tieB, near, tieA]);
  assert.deepEqual(nearby.map(item => item.community.community_id), ['near', 'a-tie', 'b-tie', 'far']);
  assert.deepEqual(nearby.map(item => item.distance), [300, 600, 600, 1200]);
});

test('nearby second-hand listing returns an empty list when nothing qualifies', () => {
  const anchor = makeCommunity('anchor', { market_state: 'new_house' });
  assert.deepEqual(nearbySecondHand(anchor, []), []);
  const faraway = makeCommunity('far', { market_state: 'second_hand', ...metersNorthOf(30.2, 120.2, 5000) });
  assert.deepEqual(nearbySecondHand(anchor, [faraway]), []);
  // 锚点无坐标时不做无意义的距离计算
  const noCoord = makeCommunity('nc', { latitude: NaN, longitude: NaN });
  assert.deepEqual(nearbySecondHand(noCoord, [faraway]), []);
});

test('the new-house price text never leaks second-hand price numbers', () => {
  const newHouse = makeCommunity('nh', {
    market_state: 'new_house',
    price: { listing_avg_price: 40659, deal_avg_price: 38500, listing_count: 23, deal_count: 5, snapshot_date: '2026-05-08' },
  });
  for (const mode of ['all', 'deal', 'listing']) {
    const text = newHousePriceText(newHouse, mode);
    assert.equal(text, '暂无价格');
    assert.doesNotMatch(text, /\d/);
    assert.ok(!text.includes('40659'));
    assert.ok(!text.includes('38500'));
  }
  // 无价小区同样走占位文案
  const noPrice = makeCommunity('nh2', {
    market_state: 'new_house',
    price: { listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '' },
  });
  assert.equal(newHousePriceText(noPrice, 'all'), '暂无价格');
});

test('the second-hand price text follows the existing price-caliber rules', () => {
  const community = makeCommunity('sh', { market_state: 'second_hand' });
  assert.match(secondHandPriceText(community, 'deal'), /38,500 元\/㎡（签约均价）/);
  assert.match(secondHandPriceText(community, 'listing'), /40,659 元\/㎡（挂牌均价）/);
  // 混合口径优先签约均价, 与 getDisplayPrice 一致
  assert.match(secondHandPriceText(community, 'all'), /38,500 元\/㎡（签约均价）/);
  const onlyListing = makeCommunity('sh2', {
    market_state: 'second_hand',
    price: { listing_avg_price: 30000, deal_avg_price: null, listing_count: 1, deal_count: 0, snapshot_date: '2026-05-08' },
  });
  assert.match(secondHandPriceText(onlyListing, 'all'), /30,000 元\/㎡（挂牌均价）/);
  const noPrice = makeCommunity('sh3', {
    market_state: 'second_hand',
    price: { listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '' },
  });
  assert.equal(secondHandPriceText(noPrice, 'all'), '暂无价格');
});
