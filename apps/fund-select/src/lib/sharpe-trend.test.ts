/**
 * 夏普走视纯逻辑测试（node --experimental-strip-types --test）
 * 覆盖：URL 参数解析、href 生成（basePath 相对路径铁律）、格式化、状态分类
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_TREND_RANGE,
  classifySharpeTrend,
  fetchSharpeTrend,
  formatRatio,
  formatSharpe,
  formatShortDate,
  formatSlope,
  parseSharpeTrendSearch,
  sharpeLevel,
  sharpeTrendHref,
  trendRangeHref,
  type SharpeTrendResponse,
} from './sharpe-trend.ts';

function response(overrides: Partial<SharpeTrendResponse> = {}): SharpeTrendResponse {
  return {
    code: '000628',
    name: '测试基金',
    range: 'all',
    rf_basis: 'zero',
    algorithm_version: 'trend-v1',
    threshold: 0.8,
    points: [
      { date: '2026-10-31', sharpe: 0.91, sample_days: 729 },
      { date: '2026-11-07', sharpe: null, sample_days: 120 },
      { date: '2026-11-12', sharpe: 0.92, sample_days: 729 },
    ],
    stats: {
      threshold: 0.8,
      current: 0.92,
      max: 1.5,
      min: 0.3,
      mean: 0.9,
      above_count: 2,
      valid_count: 2,
      above_ratio: 1,
      consecutive_above: 1,
      longest_below: 0,
      trend_12w: null,
    },
    diagnostics: { nav_end_date: '2026-11-12', total_points: 3 },
    ...overrides,
  };
}

// ─── URL 解析 ───────────────────────────────────────────────────

test('解析合法 code + range', () => {
  const s = new URLSearchParams('code=000628&range=1y');
  assert.deepEqual(parseSharpeTrendSearch(s), { code: '000628', range: '1y' });
});

test('缺失/非法 code 回退 null；非法 range 回退 all', () => {
  assert.deepEqual(parseSharpeTrendSearch(new URLSearchParams()), {
    code: null, range: DEFAULT_TREND_RANGE,
  });
  assert.deepEqual(parseSharpeTrendSearch(new URLSearchParams('code=abc&range=5y')), {
    code: null, range: 'all',
  });
  // 7 位 / 带字母 / 空串都不算合法代码
  for (const bad of ['0006281', '00062a', '']) {
    assert.equal(
      parseSharpeTrendSearch(new URLSearchParams(`code=${bad}`)).code,
      null,
      `code=${bad} 应回退`,
    );
  }
});

test('range 三个合法值都识别', () => {
  for (const r of ['all', '3y', '1y']) {
    assert.equal(
      parseSharpeTrendSearch(new URLSearchParams(`range=${r}`)).range, r,
    );
  }
});

// ─── href 生成（basePath 铁律） ─────────────────────────────────

test('sharpeTrendHref 用相对 basePath 路径，不带 /funds 前缀', () => {
  assert.equal(sharpeTrendHref('000628'), '/sharpe-trend?code=000628');
  assert.equal(
    sharpeTrendHref('000628', '1y'),
    '/sharpe-trend?code=000628&range=1y',
  );
  // 默认 all 不写 URL
  assert.equal(sharpeTrendHref('000628', 'all'), '/sharpe-trend?code=000628');
  assert.ok(!sharpeTrendHref('000628').startsWith('/funds'));
});

test('trendRangeHref 切区间保留 code', () => {
  assert.equal(trendRangeHref('002910', '3y'), '/sharpe-trend?code=002910&range=3y');
  assert.equal(trendRangeHref('002910', 'all'), '/sharpe-trend?code=002910');
});

// ─── 格式化 ─────────────────────────────────────────────────────

test('formatSharpe 2 位小数；null/NaN/Infinity → —', () => {
  assert.equal(formatSharpe(0.9163), '0.92');
  assert.equal(formatSharpe(-0.5), '-0.50');
  assert.equal(formatSharpe(null), '—');
  assert.equal(formatSharpe(undefined), '—');
  assert.equal(formatSharpe(Number.NaN), '—');
  assert.equal(formatSharpe(Number.POSITIVE_INFINITY), '—');
});

test('formatRatio 0..1 → 百分比', () => {
  // 0.565 受 IEEE754 影响 Math.round 得 56（浮点表示略小于 0.565），
  // 这里用无歧义的值断言舍入行为
  assert.equal(formatRatio(0.566), '57%');
  assert.equal(formatRatio(0.564), '56%');
  assert.equal(formatRatio(1), '100%');
  assert.equal(formatRatio(0), '0%');
  assert.equal(formatRatio(null), '—');
});

test('formatSlope 带符号 + 4 位小数 + 单位', () => {
  assert.equal(formatSlope(0.00179), '+0.0018/周');
  assert.equal(formatSlope(-0.02), '-0.0200/周');
  assert.equal(formatSlope(0), '0.0000/周');
  assert.equal(formatSlope(null), '—');
});

test('formatShortDate YYYY-MM-DD → MM-DD', () => {
  assert.equal(formatShortDate('2026-11-12'), '11-12');
  assert.equal(formatShortDate('bad'), 'bad');
});

test('sharpeLevel 按阈值分档', () => {
  assert.equal(sharpeLevel(0.8, 0.8), 'good'); // 含等号
  assert.equal(sharpeLevel(0.79, 0.8), 'bad');
  assert.equal(sharpeLevel(null, 0.8), 'na');
});

// ─── 状态分类 ───────────────────────────────────────────────────

test('classifySharpeTrend 区分四种主状态', () => {
  assert.equal(classifySharpeTrend(null), 'needs-code');
  assert.equal(
    classifySharpeTrend(response({ diagnostics: { insufficient_history: true } })),
    'insufficient',
  );
  assert.equal(
    classifySharpeTrend(response({ points: [], stats: { ...response().stats, valid_count: 0 } })),
    'no-valid',
  );
  assert.equal(classifySharpeTrend(response()), 'ok');
});

// ─── fetch 请求串（mock global fetch） ──────────────────────────

test('fetchSharpeTrend 走全路径 /funds/api/... 且默认 range 不落 URL', async () => {
  const original = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = (async (url: string | URL) => {
    urls.push(String(url));
    return new Response(JSON.stringify(response()), {
      status: 200, headers: { 'content-type': 'application/json' },
    });
  }) as typeof fetch;
  try {
    const d = await fetchSharpeTrend('000628');
    assert.equal(d.code, '000628');
    assert.deepEqual(urls, ['/funds/api/funds/sharpe-trend/000628']);
    await fetchSharpeTrend('000628', '1y');
    assert.equal(urls[1], '/funds/api/funds/sharpe-trend/000628?range=1y');
  } finally {
    globalThis.fetch = original;
  }
});

test('fetchSharpeTrend 非 2xx 抛错（可重试）', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response('净值拉取失败: network down', { status: 502 })) as typeof fetch;
  try {
    await assert.rejects(
      () => fetchSharpeTrend('000628'),
      /请求失败 502/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
