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

const {
  rentalSortValue, compareNumericMissingLast, sortRowsByRentalKey,
  indexSummaries, isRentalSortKey,
  formatUnitRentCell, formatYieldCell, formatSampleCountCell,
  rentalRefreshProgressText, rentalRefreshTerminalNote,
} = require('../src/lib/rental-dashboard.ts');
const { RentalScopeSelect, RentalSummaryCells } = require('../src/components/dashboard/RentalDashboardWidgets.tsx');
const { RentalRefreshControl } = require('../src/components/rental/RentalRefreshButton.tsx');

function summary(overrides = {}) {
  return {
    community_id: 'c1', availability: 'available', last_refresh: null,
    sample_count: 5, captured_at: '2026-10-10T10:00:00+08:00',
    unit_rent_yuan_m2_month: 45.2, annualized_gross_yield_pct: 1.69,
    ...overrides,
  };
}
function job(overrides = {}) {
  return {
    job_id: 'j1', running: true, phase: 'running',
    total_communities: 8, processed_communities: 3, current_community_id: null,
    pages_fetched: 4, details_fetched: 6, success_count: 2, failed_count: 1,
    started_at: null, finished_at: null, last_success_at: null,
    errors: { items: [], total: 0 }, result: null,
    ...overrides,
  };
}
function selectedValues(html) {
  return (html.match(/<option[^>]*>/g) || [])
    .filter(tag => /selected/.test(tag))
    .map(tag => (tag.match(/value="([^"]*)"/) || [])[1]);
}

test('rentalSortValue reads the three columns and treats zero samples as missing', () => {
  assert.equal(rentalSortValue(summary(), 'rent_unit'), 45.2);
  assert.equal(rentalSortValue(summary(), 'rent_yield'), 1.69);
  assert.equal(rentalSortValue(summary(), 'rent_samples'), 5);
  assert.equal(rentalSortValue(undefined, 'rent_unit'), null);
  assert.equal(rentalSortValue(summary({ sample_count: 0 }), 'rent_samples'), null);
  assert.equal(rentalSortValue(summary({ unit_rent_yuan_m2_month: null }), 'rent_unit'), null);
  assert.equal(rentalSortValue(summary({ annualized_gross_yield_pct: null }), 'rent_yield'), null);
});

test('compareNumericMissingLast sinks missing values regardless of order', () => {
  assert.equal(compareNumericMissingLast(null, 1, 'desc'), 1);
  assert.equal(compareNumericMissingLast(null, 1, 'asc'), 1);
  assert.equal(compareNumericMissingLast(1, null, 'desc'), -1);
  assert.equal(compareNumericMissingLast(1, null, 'asc'), -1);
  assert.equal(compareNumericMissingLast(null, null, 'desc'), 0);
  assert.equal(compareNumericMissingLast(3, 1, 'desc'), -2);
  assert.equal(compareNumericMissingLast(3, 1, 'asc'), 2);
});

test('sortRowsByRentalKey sorts values with missing always last, without mutating input', () => {
  const rows = [{ id: 'a', v: null }, { id: 'b', v: 10 }, { id: 'c', v: 30 }, { id: 'd', v: null }];
  const desc = sortRowsByRentalKey(rows, r => r.v, 'desc');
  assert.deepEqual(desc.map(r => r.id), ['c', 'b', 'a', 'd']);
  const asc = sortRowsByRentalKey(rows, r => r.v, 'asc');
  assert.deepEqual(asc.map(r => r.id), ['b', 'c', 'a', 'd']);
  assert.deepEqual(rows.map(r => r.id), ['a', 'b', 'c', 'd']); // 原数组不变
});

test('indexSummaries keys entries by community_id', () => {
  const indexed = indexSummaries([summary(), summary({ community_id: 'c2' })]);
  assert.equal(indexed.c1.sample_count, 5);
  assert.equal(indexed.c2.community_id, 'c2');
});

test('isRentalSortKey recognizes only the three rental columns', () => {
  assert.equal(isRentalSortKey('rent_unit'), true);
  assert.equal(isRentalSortKey('rent_yield'), true);
  assert.equal(isRentalSortKey('rent_samples'), true);
  assert.equal(isRentalSortKey('total_score'), false);
  assert.equal(isRentalSortKey('price'), false);
});

test('cell formatters render em dash for missing values', () => {
  assert.equal(formatUnitRentCell(null), '—');
  assert.equal(formatUnitRentCell(undefined), '—');
  assert.equal(formatUnitRentCell(45.2), '45.2');
  assert.equal(formatYieldCell(null), '—');
  assert.equal(formatYieldCell(1.69), '1.69%');
  assert.equal(formatSampleCountCell(undefined), '—');
  assert.equal(formatSampleCountCell(0), '0');
});

test('refresh progress text shows processed communities without fake percentage', () => {
  assert.equal(rentalRefreshProgressText(null), null);
  assert.equal(rentalRefreshProgressText(job()), '已处理 3/8 小区');
  assert.equal(rentalRefreshProgressText(job({ phase: 'cancelling' })), '正在取消…');
  assert.equal(rentalRefreshProgressText(job({ total_communities: 0 })), '正在准备租金更新…');
});

test('refresh terminal note covers result, cancel, interrupt and failure without publish', () => {
  assert.equal(rentalRefreshTerminalNote(null), null);
  assert.equal(rentalRefreshTerminalNote(job({ running: false, phase: 'partial_failed', result: { published: true, success_count: 5, failed_count: 2 } })),
    '上次更新：成功 5 / 失败 2');
  assert.equal(rentalRefreshTerminalNote(job({ running: false, phase: 'cancelled' })), '上次更新已取消，数据未改动');
  assert.equal(rentalRefreshTerminalNote(job({ running: false, phase: 'interrupted' })), '上次更新被中断，数据未改动');
  assert.equal(rentalRefreshTerminalNote(job({ running: false, phase: 'failed' })), '上次更新失败，数据未改动');
  assert.equal(rentalRefreshTerminalNote(job({ running: false, phase: 'succeeded', result: null })), null);
});

test('summary cells render values with reference tag, and em dashes when missing', () => {
  const present = renderToStaticMarkup(React.createElement(RentalSummaryCells, { summary: summary() }));
  assert.match(present, /45\.2/);
  assert.match(present, /1\.69%/);
  assert.match(present, /参考/);
  assert.match(present, /粗略估算/);
  assert.match(present, />5</);
  const missing = renderToStaticMarkup(React.createElement(RentalSummaryCells, { summary: undefined }));
  assert.equal((missing.match(/—/g) || []).length, 3);
  assert.doesNotMatch(missing, /参考/);
  const noYield = renderToStaticMarkup(React.createElement(RentalSummaryCells, {
    summary: summary({ annualized_gross_yield_pct: null }),
  }));
  assert.match(noYield, /—/);
  assert.doesNotMatch(noYield, /参考/);
});

test('scope select defaults to 90-144 + all bedrooms and renders options', () => {
  const html = renderToStaticMarkup(React.createElement(RentalScopeSelect, {
    scope: { areaBand: '90to144', bedrooms: 'all' },
    onChange: () => {},
  }));
  assert.deepEqual(selectedValues(html).sort(), ['90to144', 'all']);
  assert.match(html, /144㎡及以上/);
  assert.match(html, /4居及以上/);
  assert.match(html, /租金面积段/);
  assert.match(html, /租金房型/);
});

test('refresh control idle state shows start button with scope hint, no cancel', () => {
  const html = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: null, running: false, actionError: null, start: () => {}, cancel: () => {},
  }));
  assert.match(html, /更新租金/);
  assert.match(html, /更新全部已关联小区的租金数据/);
  assert.doesNotMatch(html, /取消/);
});

test('refresh control running state shows processed progress and cancel button', () => {
  const html = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: job(), running: true, actionError: null, start: () => {}, cancel: () => {},
  }));
  assert.match(html, /已处理 3\/8 小区/);
  assert.match(html, /取消/);
  assert.doesNotMatch(html, /更新租金/);
});

test('refresh control cancelling state and terminal notes render', () => {
  const cancelling = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: job({ phase: 'cancelling' }), running: true, actionError: null, start: () => {}, cancel: () => {},
  }));
  assert.match(cancelling, /正在取消…/);
  const settled = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: job({ running: false, phase: 'partial_failed', result: { published: true, success_count: 5, failed_count: 2 } }),
    running: false, actionError: null, start: () => {}, cancel: () => {},
  }));
  assert.match(settled, /成功 5 \/ 失败 2/);
  const failed = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: job({ running: false, phase: 'failed' }), running: false, actionError: null, start: () => {}, cancel: () => {},
  }));
  assert.match(failed, /上次更新失败，数据未改动/);
});

test('refresh control surfaces action errors like 409/422 feedback', () => {
  const html = renderToStaticMarkup(React.createElement(RentalRefreshControl, {
    job: null, running: false,
    actionError: '已有租金更新任务在运行，请稍后再试',
    start: () => {}, cancel: () => {},
  }));
  assert.match(html, /role="alert"/);
  assert.match(html, /已有租金更新任务在运行，请稍后再试/);
});
