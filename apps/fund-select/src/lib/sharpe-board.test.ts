/**
 * 夏普榜单纯逻辑测试（node --experimental-strip-types --test）
 * 覆盖：URL 参数解析/序列化往返、非法值回退、请求查询串、状态分类、profile 文案
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_SHARPE_FILTERS,
  classifySharpeBoard,
  consecutiveWeeksTip,
  describeEntryFilters,
  describePrefilters,
  formatListedWeeks,
  hasPointInRange,
  listedWeeksTip,
  parseSharpeFiltersFromSearch,
  RANGE_OPTIONS,
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
    diagnostics: { no_board_weeks: [], gap_weeks: [], latest_diagnostics: {} },
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
    profileVersion: 'v1',  // 非默认值（默认已切 v3）
    minLatestSharpe: 0.9,
    minListedPct: 80,
    latestOnly: true,
    range: '3m' as const,
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
    min_listed_pct: '120',
    range: '2y',
    page: '-1',
    limit: '999',
  }));
  assert.equal(parsed.source, 'all');
  assert.equal(parsed.minLatestSharpe, null);
  assert.equal(parsed.minListedPct, 60);
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
  assert.equal(params.get('source'), 'all');
  assert.equal(params.get('profile_version'), 'v3');  // 默认已切 v3
  assert.equal(params.get('range'), 'all');
  assert.equal(params.get('page'), '1');
  assert.equal(params.get('limit'), '50');
  assert.equal(params.get('min_listed_pct'), '60');
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
  assert.equal(sharpeFiltersActive({ ...DEFAULT_SHARPE_FILTERS, minListedPct: 80 }), true);
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

test('describeEntryFilters：v2 三道新门全部渲染', () => {
  const profile = {
    ...response().profile,
    version: 'v2',
    algorithm_version: 'risk-3y-v2',
    filters: {
      ...response().profile.filters,
      min_ir: 0.5,
      min_sample_days: 700,
      max_peer_pct: 20,
    },
  };
  const parts = describeEntryFilters(profile);
  assert.ok(parts.includes('信息比率 IR ≥ 0.5'));
  assert.ok(parts.includes('样本交易日 ≥ 700 天'));
  assert.ok(parts.includes('近三年同类排名前 20%'));
  // v1 五条件仍保留
  assert.ok(parts.includes('近三年夏普 ≥ 0.8'));
});

test('默认筛选使用 v3 规则版本', () => {
  assert.equal(DEFAULT_SHARPE_FILTERS.profileVersion, 'v3');
  const q = sharpeFiltersToQuery(DEFAULT_SHARPE_FILTERS);
  assert.equal(new URLSearchParams(q).get('profile_version'), 'v3');
});

test('describeEntryFilters：v3 年度同类排名门槛文案', () => {
  const profile = {
    ...response().profile,
    version: 'v3',
    filters: {
      ...response().profile.filters,
      min_ir: 0.5,
      min_sample_days: 700,
      min_yearly_top_pct: 25,
      min_yearly_years: 2,
    },
  };
  delete (profile.filters as Record<string, unknown>).max_peer_pct;
  const parts = describeEntryFilters(profile);
  assert.ok(parts.includes('近 3 个完整年度中至少 2 年同类排名前 25%'));
  // 不再出现 v2 的滚动口径文案
  assert.ok(!parts.some(p => p.includes('近三年同类排名前')));
});

// ── 数据缺口周口径（11-14-sharpe-board-gap-weeks）────────────────────────────

test('在榜列文案：在榜/可评（分母 = 该基金有有效样本的周数）', () => {
  assert.equal(formatListedWeeks(51, 51), '51/51');
  assert.equal(formatListedWeeks(50, 51), '50/51');
  assert.equal(formatListedWeeks(8, 52), '8/52');
  // 老后端没有可评周数 → 只显示在榜周数（不显示 "51/0"）
  assert.equal(formatListedWeeks(51, null), '51');
  assert.equal(formatListedWeeks(51, 0), '51');
});

test('在榜列 tooltip：说明分母口径 + 列出数据缺口周', () => {
  const tip = listedWeeksTip(51, 51, ['2026-02-16']);
  assert.match(tip, /51\/51/);
  assert.match(tip, /可评 51 周/);
  assert.match(tip, /2026-02-16/);
  assert.match(tip, /不打断连续/);
  // 无缺口周 → 不提缺口
  assert.doesNotMatch(listedWeeksTip(51, 51, []), /数据缺口周/);
});

test('连续周数 tooltip：数据缺口不打断连续 + 列出缺口周', () => {
  const tip = consecutiveWeeksTip(51, ['2026-02-16']);
  assert.match(tip, /最近连续 51 周/);
  assert.match(tip, /数据缺口周跳过、不中断/);
  assert.match(tip, /真实缺席/);
  assert.match(tip, /2026-02-16/);
  assert.doesNotMatch(consecutiveWeeksTip(32, []), /数据缺口周：/);
});

// ── 在榜占比筛选 + 时间范围精简（11-14-sharpe-board-listed-pct-filter）────────

test('在榜占比下限：默认 60%，URL 往返，越界回落默认', () => {
  assert.equal(DEFAULT_SHARPE_FILTERS.minListedPct, 60);
  const parsed = parseSharpeFiltersFromSearch(new URLSearchParams({ min_listed_pct: '80' }));
  assert.equal(parsed.minListedPct, 80);
  const roundTrip = parseSharpeFiltersFromSearch(
    sharpeFiltersToSearch({ ...DEFAULT_SHARPE_FILTERS, minListedPct: 80 }),
  );
  assert.equal(roundTrip.minListedPct, 80);
  // 越界回落默认
  assert.equal(
    parseSharpeFiltersFromSearch(new URLSearchParams({ min_listed_pct: '120' })).minListedPct,
    60,
  );
  assert.equal(
    parseSharpeFiltersFromSearch(new URLSearchParams({ min_listed_pct: '-5' })).minListedPct,
    60,
  );
  // 默认值不写进 URL
  assert.equal(sharpeFiltersToSearch(DEFAULT_SHARPE_FILTERS).get('min_listed_pct'), null);
});

test('旧参数 min_weeks 已下线：旧链接落到默认 60%', () => {
  const parsed = parseSharpeFiltersFromSearch(new URLSearchParams({ min_weeks: '3' }));
  assert.equal(parsed.minListedPct, 60);
});

test('时间范围：去掉与「近一年(52周)」重复的「近 1 年」，只留 3 项', () => {
  assert.deepEqual(RANGE_OPTIONS.map(o => o.value), ['3m', '6m', 'all']);
  assert.ok(!RANGE_OPTIONS.some(o => (o.value as string) === '1y'));
  // 旧链接 ?range=1y → 回落默认（同样 52 周视图，行为不变）
  const parsed = parseSharpeFiltersFromSearch(new URLSearchParams({ range: '1y' }));
  assert.equal(parsed.range, 'all');
});
