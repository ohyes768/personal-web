/**
 * 夏普榜单纯逻辑测试（node --experimental-strip-types --test）
 * 覆盖：URL 参数解析/序列化往返、非法值回退、请求查询串、状态分类、profile 文案
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_SHARPE_FILTERS,
  classifySharpeBoard,
  describeEntryFilters,
  describePrefilters,
  hasPointInRange,
  parseSharpeFiltersFromSearch,
  sharpeFiltersActive,
  sharpeFiltersToQuery,
  sharpeFiltersToSearch,
  type SharpeBoardResponse,
} from './sharpe-board.ts';

function response(overrides: Partial<SharpeBoardResponse> = {}): SharpeBoardResponse {
  return {
    profile: {
      source: 'discovery-stock',
      version: 'v1',
      filters: {
        min_age: 3,
        min_size_yi: 5,
        max_dd_3y: 30,
        min_mgr_exp: 5,
        min_sharpe: 0.8,
        exclude_qdii: false,
      },
      collection_prefilters: {},
      market_subtypes: null,
      algorithm_version: 'risk-3y-v1',
    },
    latest_published_week: null,
    latest_attempt: null,
    stale: true,
    total: 0,
    items: [],
    weeks: [],
    series: [],
    diagnostics: { no_board_weeks: [], latest_diagnostics: {} },
    ...overrides,
  };
}

test('空参数解析为默认筛选', () => {
  const filters = parseSharpeFiltersFromSearch(new URLSearchParams());
  assert.deepEqual(filters, DEFAULT_SHARPE_FILTERS);
});

test('URL 参数往返：非默认值全部保留', () => {
  const filters = {
    ...DEFAULT_SHARPE_FILTERS,
    source: 'stock' as const,
    profileVersion: 'v2',
    minLatestSharpe: 0.9,
    minWeeks: 3,
    latestOnly: true,
    range: '1y' as const,
    page: 2,
    limit: 25,
  };
  const parsed = parseSharpeFiltersFromSearch(sharpeFiltersToSearch(filters));
  assert.deepEqual(parsed, filters);
});

test('非法值逐字段回退默认', () => {
  const parsed = parseSharpeFiltersFromSearch(new URLSearchParams({
    source: 'bond',
    min_latest_sharpe: '99',
    min_weeks: '0',
    range: '2y',
    page: '-1',
    limit: '999',
  }));
  assert.equal(parsed.source, 'discovery-stock');
  assert.equal(parsed.minLatestSharpe, null);
  assert.equal(parsed.minWeeks, 1);
  assert.equal(parsed.range, 'all');
  assert.equal(parsed.page, 1);
  assert.equal(parsed.limit, 50);
});

test('min_latest_sharpe 支持负数与边界 -10/10（含等于的展示下限）', () => {
  const neg = parseSharpeFiltersFromSearch(new URLSearchParams({ min_latest_sharpe: '-1.5' }));
  assert.equal(neg.minLatestSharpe, -1.5);
  const low = parseSharpeFiltersFromSearch(new URLSearchParams({ min_latest_sharpe: '-10' }));
  assert.equal(low.minLatestSharpe, -10);
  const high = parseSharpeFiltersFromSearch(new URLSearchParams({ min_latest_sharpe: '10' }));
  assert.equal(high.minLatestSharpe, 10);
});

test('请求查询串始终显式携带 source/range/分页', () => {
  const q = sharpeFiltersToQuery(DEFAULT_SHARPE_FILTERS);
  const params = new URLSearchParams(q);
  assert.equal(params.get('source'), 'discovery-stock');
  assert.equal(params.get('profile_version'), 'v1');
  assert.equal(params.get('range'), 'all');
  assert.equal(params.get('page'), '1');
  assert.equal(params.get('limit'), '50');
  assert.equal(params.get('min_weeks'), '1');
  assert.equal(params.get('min_latest_sharpe'), null);
  assert.equal(q.startsWith('?'), true);
});

test('classify：库空 → no-data', () => {
  const phase = classifySharpeBoard(response(), false);
  assert.equal(phase, 'no-data');
});

test('classify：无筛选零命中 → empty-board（成功空榜/失败无榜）', () => {
  const data = response({
    latest_attempt: {
      week_start: '2026-11-02',
      status: 'complete',
      trigger: 'scheduled',
      started_at: '2026-11-07T08:05:00+08:00',
      finished_at: null,
      selected_count: 0,
      errors: [],
    },
  });
  assert.equal(classifySharpeBoard(data, false), 'empty-board');
});

test('classify：筛选筛空 → no-match', () => {
  const data = response({
    latest_attempt: {
      week_start: '2026-11-02',
      status: 'complete',
      trigger: 'manual',
      started_at: null,
      finished_at: null,
      selected_count: 5,
      errors: [],
    },
  });
  assert.equal(classifySharpeBoard(data, true), 'no-match');
});

test('classify：有命中 → ok', () => {
  const data = response({
    total: 2,
    latest_attempt: {
      week_start: '2026-11-02',
      status: 'complete',
      trigger: 'scheduled',
      started_at: null,
      finished_at: null,
      selected_count: 2,
      errors: [],
    },
  });
  assert.equal(classifySharpeBoard(data, true), 'ok');
});

test('sharpeFiltersActive：默认不激活，任一展示筛选激活', () => {
  assert.equal(sharpeFiltersActive(DEFAULT_SHARPE_FILTERS), false);
  assert.equal(sharpeFiltersActive({ ...DEFAULT_SHARPE_FILTERS, minLatestSharpe: 1 }), true);
  assert.equal(sharpeFiltersActive({ ...DEFAULT_SHARPE_FILTERS, minWeeks: 2 }), true);
  assert.equal(sharpeFiltersActive({ ...DEFAULT_SHARPE_FILTERS, latestOnly: true }), true);
  // range 只裁图，不算筛选激活
  assert.equal(sharpeFiltersActive({ ...DEFAULT_SHARPE_FILTERS, range: '3m' }), false);
});

test('hasPointInRange：范围内无点为 false，任意一点为 true', () => {
  assert.equal(hasPointInRange([{ code: 'A', name: 'A', values: [null, null] }]), false);
  assert.equal(hasPointInRange([{ code: 'A', name: 'A', values: [null, 1.05] }]), true);
});

test('describeEntryFilters：按 profile 渲染入选条件', () => {
  const profile = response().profile;
  const parts = describeEntryFilters(profile);
  assert.ok(parts.includes('成立 ≥ 3 年'));
  assert.ok(parts.includes('规模 ≥ 5 亿'));
  assert.ok(parts.includes('近三年回撤绝对值 ≤ 30%'));
  assert.ok(parts.includes('经理从业 ≥ 5 年'));
  assert.ok(parts.includes('近三年夏普 ≥ 0.8'));
  assert.ok(!parts.includes('排除 QDII'));
});

test('describePrefilters：市场来源有预筛约束，雪球来源为空', () => {
  const market = {
    ...response().profile,
    collection_prefilters: { min_ret_3y: 20, min_size_yi: 5, min_mgr_exp: 5 },
  };
  const parts = describePrefilters(market);
  assert.ok(parts.includes('近三年收益 ≥ 20%'));
  assert.equal(describePrefilters(response().profile).length, 0);
});
