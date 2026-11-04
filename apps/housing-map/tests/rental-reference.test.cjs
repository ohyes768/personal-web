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

const { isTerminalPhase, buildRentalDetailPath } = require('../src/lib/rental-types.ts');
const { CommunityRentalMetricsContent } = require('../src/components/community/CommunityRentalMetrics.tsx');

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
      source_url: 'https://m.xflapp.com/zufang/hz-1.html', captured_at: '2026-10-10',
    }],
    page: 1, page_size: 10, total: 1,
    source_links: ['https://m.xflapp.com/zufang/hz-1.html'],
    ...overrides,
  };
}

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

test('overview uses merged area group rather than an individual bedroom yield', () => {
  const individual = availableData().groups[0];
  const data = availableData({ groups: [individual, {
    ...individual, bedrooms: null,
    yield_estimate: { rent_to_sale_ratio: 500, annualized_gross_yield_pct: 2.4 },
  }] });
  const html = renderToStaticMarkup(React.createElement(CommunityRentalMetricsContent, { data }));
  assert.match(html, />1:500</);
  assert.match(html, />2\.40%</);
  assert.doesNotMatch(html, />1:708</);
  assert.match(html, /title="90–144㎡/);
  assert.doesNotMatch(html, /<p|rental-meta/);
});

test('overview hides estimates for stale or insufficient samples and exposes the reason', () => {
  for (const [availability, reason] of [['stale', '超过30天'], ['insufficient_samples', '不足3套']]) {
    const individual = availableData().groups[0];
    const data = availableData({ availability, groups: [{ ...individual, bedrooms: null }] });
    const html = renderToStaticMarkup(React.createElement(CommunityRentalMetricsContent, { data }));
    assert.equal((html.match(/>—</g) ?? []).length, 2);
    assert.match(html, new RegExp(reason));
  }
});

test('overview does not substitute bedroom group when merged group is missing', () => {
  const html = renderToStaticMarkup(React.createElement(CommunityRentalMetricsContent, { data: availableData() }));
  assert.equal((html.match(/>—</g) ?? []).length, 2);
});
