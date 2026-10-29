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
const { default: NewHouseDetail } = require('../src/components/community/NewHouseDetail.tsx');
const { default: NearbySecondHandList } = require('../src/components/community/NearbySecondHandList.tsx');

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

const NEW_HOUSE = {
  market_state: 'new_house',
  project: {
    project_id: '2313460053',
    project_name: '云栖名苑',
    sale_status: '在售',
    identity_url: 'https://example.com/project/2313460053',
    captured_at: '2026-10-28',
  },
  position: { source: 'amap', verified: true, address: '滨文路与浦沿路交叉口' },
};

function renderDetail(community, extra = {}) {
  return renderToStaticMarkup(React.createElement(NewHouseDetail, {
    community,
    priceMode: 'all',
    onClose() {},
    nearbyOpen: false,
    nearbyCommunities: [],
    nearbyConditions: '名称不限 · 全部区域 · 全部物业类型',
    onToggleNearby() {},
    onSelectNearby() {},
    ...extra,
  }));
}

test('the new-house detail states the sale status, project identity and price caliber', () => {
  const html = renderDetail(makeCommunity('nh', NEW_HOUSE));
  assert.match(html, /在售/);
  assert.match(html, /云栖名苑/);
  assert.match(html, /2313460053/);
  assert.match(html, /查看项目来源/);
  assert.match(html, /href="https:\/\/example\.com\/project\/2313460053"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  // 新房价格恒为暂无, 且明确说明没有可靠项目价格
  assert.match(html, /暂无价格/);
  assert.match(html, /暂无可靠项目价格/);
  // 二手房的租售收益/成交套数/综合评分不能出现在新房详情里
  assert.doesNotMatch(html, /挂牌均价|签约均价|在售套数|近月签约|综合评分|租金与收益/);
});

test('an unverified or missing position is stated explicitly instead of being implied', () => {
  const pending = renderDetail(makeCommunity('nh2', {
    market_state: 'new_house',
    project: { project_id: 'p2', project_name: null, sale_status: null, identity_url: null, captured_at: null },
    position: { source: 'amap', verified: false, address: null },
  }));
  assert.match(pending, /位置待核实/);
  assert.match(pending, /暂无/);          // 销售状态/项目名称/所在地都缺
  assert.match(pending, /暂无位置资料|位置待核实/);
  assert.doesNotMatch(pending, /位置已核验/);

  const historical = renderDetail(makeCommunity('nh3', {
    market_state: 'new_house',
    project: { project_id: 'p3', project_name: null, sale_status: '售完', identity_url: null, captured_at: null },
    position: { source: 'historical_amap', verified: false, address: '历史地址' },
  }));
  assert.match(historical, /历史快照/);
  assert.match(historical, /位置待核实/);
  assert.match(historical, /不代表本次重新核验/);

  const noPosition = renderDetail(makeCommunity('nh4', { market_state: 'new_house' }));
  assert.match(noPosition, /暂无位置资料/);
  assert.doesNotMatch(noPosition, /位置已核验/);
});

test('the nearby list shows distances, prices and the applied limits', () => {
  const anchor = makeCommunity('anchor', NEW_HOUSE);
  const near = makeCommunity('near', { market_state: 'second_hand', latitude: 30.21, longitude: 120.2 });
  const html = renderToStaticMarkup(React.createElement(NearbySecondHandList, {
    anchor,
    communities: [anchor, near],
    priceMode: 'all',
    conditions: '名称不限 · 全部区域 · 全部物业类型',
    onSelect() {},
  }));
  assert.match(html, /附近二手房（1）/);
  assert.match(html, /1\.5 公里直线距离/);
  assert.match(html, /当前筛选：/);
  assert.match(html, /名称不限/);
  assert.match(html, /小区near/);
  assert.match(html, /米/);
  assert.match(html, /38,500 元\/㎡（签约均价）/);
  assert.match(html, /价格日期 2026-05-08/);
  // 列表项必须能用键盘操作
  assert.match(html, /<button[^>]*class="nh-nearby-item"/);
});

test('the nearby list explains an empty result instead of inventing data', () => {
  const anchor = makeCommunity('anchor', NEW_HOUSE);
  const far = makeCommunity('far', { market_state: 'second_hand', latitude: 30.3, longitude: 120.2 });
  const html = renderToStaticMarkup(React.createElement(NearbySecondHandList, {
    anchor,
    communities: [anchor, far],
    priceMode: 'all',
    conditions: '名称不限 · 全部区域 · 全部物业类型',
    onSelect() {},
  }));
  assert.match(html, /附近二手房（0）/);
  assert.match(html, /附近 1\.5 公里内没有符合条件的二手房/);
  assert.match(html, /放宽/);
  assert.doesNotMatch(html, /小区far/);
});

test('a nearby listing without a price still enters the list', () => {
  const anchor = makeCommunity('anchor', NEW_HOUSE);
  const noPrice = makeCommunity('np', {
    market_state: 'second_hand',
    latitude: 30.21,
    longitude: 120.2,
    price: { listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '' },
  });
  const html = renderToStaticMarkup(React.createElement(NearbySecondHandList, {
    anchor,
    communities: [anchor, noPrice],
    priceMode: 'all',
    conditions: '名称不限 · 全部区域 · 全部物业类型',
    onSelect() {},
  }));
  assert.match(html, /附近二手房（1）/);
  assert.match(html, /小区np/);
  assert.match(html, /暂无价格/);
});
