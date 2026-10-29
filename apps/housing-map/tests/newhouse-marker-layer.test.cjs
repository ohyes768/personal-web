/* eslint-disable @typescript-eslint/no-require-imports */
// 新房项目点图层的纯函数测试: 标记内容、实心/空心与缩放收起项目名。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const {
  NEW_HOUSE_COLOR, NEW_HOUSE_LABEL_MIN_ZOOM,
  buildNewHouseMarkerContent, escapeHtml, newHouseLabel,
} = require('../src/components/map/NewHouseLayer.tsx');

function makeCommunity(overrides = {}) {
  return {
    community_id: 'c1',
    community_name: '钱塘山水',
    district: '滨江',
    subdistrict: '浦沿',
    address: '滨文路',
    latitude: 30.2,
    longitude: 120.2,
    price: { listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '' },
    pois: [],
    score: { total_score: 0, location_score: null, amenity_score: null, product_score: null, market_score: null },
    ...overrides,
  };
}

test('a new-house marker never uses the second-hand price scale colour', () => {
  const html = buildNewHouseMarkerContent({ name: '测试项目', verified: true, selected: false, showName: true });
  assert.ok(html.includes(NEW_HOUSE_COLOR));
  // 二手房价格色阶的档位色不应出现在新房标记里
  for (const priceColour of ['#3D9147', '#A8C03C', '#E5B32C', '#E2711D', '#D64545', '#9AA3AD']) {
    assert.ok(!html.includes(priceColour), `新房标记不应含二手房价格色 ${priceColour}`);
  }
  assert.ok(!html.includes('★'));
});

test('the badge is solid when the position is verified and hollow otherwise', () => {
  const solid = buildNewHouseMarkerContent({ name: '项目', verified: true, selected: false, showName: true });
  const hollow = buildNewHouseMarkerContent({ name: '项目', verified: false, selected: false, showName: true });
  assert.ok(solid.includes(`background:${NEW_HOUSE_COLOR};color:#fff`));
  assert.ok(hollow.includes('border:1.5px dashed'));
  assert.notEqual(solid, hollow);
});

test('the project name is only rendered when the zoom level asks for it', () => {
  const compact = buildNewHouseMarkerContent({ name: '项目名', verified: true, selected: false, showName: false });
  const full = buildNewHouseMarkerContent({ name: '项目名', verified: true, selected: false, showName: true });
  assert.ok(!compact.includes('项目名'));
  assert.ok(full.includes('项目名'));
  // 两种形态都保留「新」字, 缩小后仍能看出房源类型
  assert.ok(compact.includes('新'));
  assert.ok(full.includes('新'));
  assert.ok(NEW_HOUSE_LABEL_MIN_ZOOM >= 12);
});

test('the marker escapes the project name before it reaches the HTML string', () => {
  const html = buildNewHouseMarkerContent({ name: '<img src=x onerror=alert(1)>', verified: true, selected: false, showName: true });
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
});

test('the marker label prefers the project name and falls back to the community name', () => {
  assert.equal(newHouseLabel(makeCommunity({ project: { project_id: 'p1', project_name: '云栖名邸', sale_status: '在售', identity_url: null, captured_at: null } })), '云栖名邸');
  assert.equal(newHouseLabel(makeCommunity()), '钱塘山水');
  assert.equal(newHouseLabel(makeCommunity({ project: { project_id: 'p1', project_name: '  ', sale_status: null, identity_url: null, captured_at: null } })), '钱塘山水');
});

test('html escaping covers the characters that break the marker markup', () => {
  assert.equal(escapeHtml('a&b<c>"d"\'e'), 'a&amp;b&lt;c&gt;&quot;d&quot;&#39;e');
});
