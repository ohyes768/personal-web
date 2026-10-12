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

const { RentalReferenceContent } = require('../src/components/community/CommunityRentalReference.tsx');
const { isTerminalPhase, buildRentalDetailPath } = require('../src/lib/rental-types.ts');

function rentReference(overrides = {}) {
  return {
    median_month_rent_yuan: 4500, median_unit_rent_yuan_m2_month: 45.2,
    p25_unit_rent_yuan_m2_month: 40.1, p75_unit_rent_yuan_m2_month: 51.3, sample_count: 5,
    ...overrides,
  };
}
function availableData(overrides = {}) {
  return {
    availability: 'available', last_refresh: null,
    sample_count: 5, excluded_count: 2, captured_at: '2026-10-10T10:00:00+08:00',
    groups: [{
      bedrooms: 2, area_band: '90to144', sample_count: 5,
      rent_reference: rentReference(),
      sale_reference: { unit_price_yuan_m2: 32000, price_kind: 'signed', price_date: '2026-09-30' },
      yield_estimate: { annualized_gross_yield_pct: 1.69, rent_to_sale_ratio: 708.0 },
    }],
    bedrooms_distribution: { '2': 4, '3': 1 },
    samples: [{
      source_listing_id: 'f1', title: '整租·两房', bedrooms: 2, area_m2: 89,
      month_rent_yuan: 4500, unit_rent_yuan_m2_month: 50.6,
      source_url: 'https://zu.fang.com/house/f1.html', captured_at: '2026-10-10',
    }],
    page: 1, page_size: 10, total: 1,
    source_links: ['https://zu.fang.com/house/'],
    ...overrides,
  };
}

test('available data shows group metrics, yield estimate labels and disclosure', () => {
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data: availableData() }));
  assert.match(html, /2 居室 · 90–144㎡/);
  assert.match(html, /4,500 元\/月/);
  assert.match(html, /45\.2 元\/㎡\/月/);
  assert.match(html, /40\.1 ~ 51\.3/);
  assert.match(html, /粗略估算/);
  assert.match(html, /并非同户型成交/);
  assert.match(html, /约 1\.69%/);
  assert.match(html, /1 : 708/);
  assert.match(html, /近期签约价/);
  assert.match(html, /房型分布：2居×4、3居×1/);
  assert.match(html, /href="https:\/\/zu\.fang\.com\/house\/f1\.html"/);
});

test('unmapped availability explains missing mapping', () => {
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, {
    data: availableData({ availability: 'unmapped', groups: [], samples: [], source_links: [] }),
  }));
  assert.match(html, /尚未关联租金来源/);
  assert.doesNotMatch(html, /粗略估算/);
});

test('insufficient samples shows detail-only notice without yield numbers', () => {
  const data = availableData({
    availability: 'insufficient_samples',
    groups: [{ bedrooms: 2, area_band: '90to144', sample_count: 2, rent_reference: null, sale_reference: null, yield_estimate: null }],
  });
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data }));
  assert.match(html, /有效样本不足 3 条/);
  assert.match(html, /样本不足 3 条，仅展示明细/);
  assert.doesNotMatch(html, /年化毛收益率/);
});

test('stale availability keeps samples but disables yield estimate', () => {
  const data = availableData({
    availability: 'stale',
    groups: [{
      bedrooms: 2, area_band: '90to144', sample_count: 5,
      rent_reference: rentReference(), sale_reference: { unit_price_yuan_m2: 32000, price_kind: 'listing', price_date: '2026-09-30' },
      yield_estimate: null,
    }],
  });
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data }));
  assert.match(html, /超过 30 天未更新/);
  assert.match(html, /收益率估算已停用/);
  assert.match(html, /4,500 元\/月/); // 明细仍可见
  assert.doesNotMatch(html, /年化毛收益率/);
});

test('stale history data coexists with last refresh failure notice', () => {
  const data = availableData({
    last_refresh: { status: 'failed', finished_at: '2026-10-12T09:00:00+08:00', error: '详情页验证失败' },
  });
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data }));
  assert.match(html, /最近一次租金更新失败/);
  assert.match(html, /详情页验证失败/);
  assert.match(html, /历史数据/);
  assert.match(html, /4,500 元\/月/); // 旧数据仍展示
});

test('excluded view renders exclusion reasons, valid view does not', () => {
  const data = availableData({
    samples: [{
      source_listing_id: 'f9', title: '疑似分割出租', bedrooms: 3, area_m2: 89,
      month_rent_yuan: 6800, unit_rent_yuan_m2_month: 76.4,
      source_url: null, captured_at: '2026-10-10', exclude_reason: '疑似分割出租',
    }],
  });
  const excludedHtml = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data, view: 'excluded' }));
  assert.match(excludedHtml, /排除理由：疑似分割出租/);
  const validHtml = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data, view: 'valid' }));
  assert.doesNotMatch(validHtml, /排除理由/);
});

test('source links restricted to zu.fang.com https domain', () => {
  const data = availableData({
    samples: [{
      source_listing_id: 'fx', title: null, bedrooms: null, area_m2: null,
      month_rent_yuan: null, unit_rent_yuan_m2_month: null,
      source_url: 'javascript:alert(1)', captured_at: null,
    }],
    source_links: ['http://evil.example.com/list'],
  });
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, { data }));
  assert.doesNotMatch(html, /href="javascript:/);
  assert.doesNotMatch(html, /evil\.example\.com" ?/);
  assert.doesNotMatch(html, /<a /);
});

test('no_samples availability differs from unmapped', () => {
  const html = renderToStaticMarkup(React.createElement(RentalReferenceContent, {
    data: availableData({ availability: 'no_samples', groups: [], samples: [], source_links: [] }),
  }));
  assert.match(html, /没有可用房源样本/);
});

test('terminal refresh phases stop polling, non-terminal keep polling', () => {
  assert.equal(isTerminalPhase('succeeded'), true);
  assert.equal(isTerminalPhase('partial_failed'), true);
  assert.equal(isTerminalPhase('failed'), true);
  assert.equal(isTerminalPhase('cancelled'), true);
  assert.equal(isTerminalPhase('interrupted'), true);
  assert.equal(isTerminalPhase('running'), false);
  assert.equal(isTerminalPhase('cancelling'), false);
});

test('detail request path encodes community id and query params', () => {
  const path = buildRentalDetailPath('10001742', { areaBand: '90to144', bedrooms: 'all', page: 2, view: 'excluded' });
  assert.equal(path, 'communities/10001742/rentals?area_band=90to144&bedrooms=all&view=excluded&page=2&page_size=10');
  const encoded = buildRentalDetailPath('a b/c', { areaBand: 'all', bedrooms: '4plus', page: 1, view: 'valid' });
  assert.match(encoded, /^communities\/a%20b%2Fc\/rentals\?/);
});
