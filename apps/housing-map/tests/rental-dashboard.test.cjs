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
  rentalRefreshDiagnostics,
} = require('../src/lib/rental-dashboard.ts');

test('rental diagnostics distinguish reused data and cooldown from fresh success', () => {
  assert.equal(rentalRefreshDiagnostics({}), null);
  const note = rentalRefreshDiagnostics({ request_count: 1, detail_cache_hits: 5, reused_communities: 2,
    deferred_count: 3, cooldown_until: '2026-10-18T10:00:00+00:00', new_sources_deferred: 1 });
  assert.match(note, /请求 1 次/);
  assert.match(note, /详情复用 5 条/);
  assert.match(note, /快照复用 2 个小区/);
  assert.match(note, /未采集 3 个小区/);
  assert.match(note, /冷却至/);
  assert.match(note, /新关联 1 个，下轮采集/);
});
const { RentalScopeSelect, RentalSummaryCells } = require('../src/components/dashboard/RentalDashboardWidgets.tsx');
const { CollectionControls, normalizeCollectionJob } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
function renderRent(value, error) {
  return renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, pipeline: true, scope: 'maintenance', action() {},
    jobs: { rent: normalizeCollectionJob(value) }, errors: error ? { rent: error } : {},
  }));
}

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

test('central rental task offers start and preserves its residential scope', () => {
  const html = renderRent(null);
  assert.match(html, /更新租金数据/);
  assert.match(html, /仅已收录住宅/);
  assert.doesNotMatch(html, /停止更新租金/);
});

test('central rental task normalizes progress and offers cancellation', () => {
  const html = renderRent(job());
  assert.match(html, /已处理 3 \/ 8/);
  assert.match(html, /停止更新租金/);
});

test('central rental task reports cancelling, partial and failed phases', () => {
  assert.match(renderRent(job({ phase: 'cancelling' })), /正在取消/);
  assert.match(renderRent(job({ running: false, phase: 'partial_failed' })), /部分完成/);
  assert.match(renderRent(job({ running: false, phase: 'failed' })), /采集失败/);
});

test('central rental task keeps actionable API errors visible', () => {
  const html = renderRent(null, '已有租金更新任务在运行，请稍后再试');
  assert.match(html, /role="alert"/);
  assert.match(html, /已有租金更新任务在运行，请稍后再试/);
});

test('rental source checks separate missing, failed and unqueried communities', () => {
  assert.equal(rentalRefreshProgressText(job({ stage: 'checking' })), '正在检查租金来源…');
  const association = { targets: 20, checked: 3, matched: 1, pending: 2, missing: 5, failed: 6, deferred: 7 };
  assert.equal(rentalRefreshProgressText(job({ stage: 'discovering', association })), '正在查找来源 3/20 小区');
  const html = renderRent(job({ running: false, phase: 'partial_failed', association }));
  assert.match(html, /未找到 5/);
  assert.match(html, /查询失败 6/);
  assert.match(html, /未查询 7/);
});

test('deferred-only rentals are unqueried rather than failed', () => {
  const html = renderRent(job({ running: false, phase: 'partial_failed', association: { checked: 4, failed: 0, deferred: 4 } }));
  assert.match(html, /查询失败 0/);
  assert.match(html, /未查询 4/);
  const { RentalCandidateChoice } = require('../src/components/rental/RentalAssociationReview.tsx');
  const review = renderToStaticMarkup(React.createElement(RentalCandidateChoice, {
    item: { community_id: 'c1', community_name: '测试花园', reason: 'search_deferred', candidates: [] },
    selected: '', busy: false, onSelect() {}, onDecide() {},
  }));
  assert.match(review, /尚未查询，下次更新继续/);
  assert.doesNotMatch(review, /来源查找失败/);
});

test('review sends homepage selection to Xingfuli and preserves skip/reopen', () => {
  const { RentalCandidateChoice } = require('../src/components/rental/RentalAssociationReview.tsx');
  const item = { community_id: 'c1', community_name: '东方郡', reason: 'needs_selection', candidates: [
    { id: 'east', name: '东方郡东区', address: '东区地址' }, { id: 'west', name: '东方郡西区' },
  ] };
  const render = (selected, reason = item.reason) => renderToStaticMarkup(React.createElement(RentalCandidateChoice, {
    item: { ...item, reason }, selected, busy: false, onSelect() {}, onDecide() {},
  }));
  const empty = render('');
  assert.equal((empty.match(/type="radio"/g) || []).length, 0);
  assert.doesNotMatch(empty, /绑定所选小区|房天下/);
  assert.match(empty, /幸福里主页/);
  assert.match(empty, /暂时跳过/);
  assert.doesNotMatch(empty, /type="checkbox"|贴链接|粘贴/);
  assert.doesNotMatch(render('east'), /checked=""/);
  assert.match(render('', 'skipped'), /重新处理/);
});
