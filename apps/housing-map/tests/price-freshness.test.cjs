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

const {
  monthLabel, shortDate, normalizePriceBlock, normalizeRefreshJob, normalizeRefreshCounts,
  refreshPhaseText, refreshSummaryMetrics, refreshStatusLine, dualPriceLines,
  refreshJobFromStartPayload,
} = require('../src/lib/price-freshness.ts');
const PriceDetails = require('../src/components/community/PriceDetails.tsx').default;
const PriceRefreshControls = require('../src/components/community/PriceRefreshControls.tsx').default;

test('month label and captured date derivation never invent data', () => {
  assert.equal(monthLabel('2026-10'), '2026年10月');
  assert.equal(monthLabel('2026-13'), null);
  assert.equal(monthLabel('2026-5'), null);
  assert.equal(monthLabel('2026年10月'), null);
  assert.equal(monthLabel(null), null);
  assert.equal(shortDate('2026-10-28T02:31:00.000Z'), '2026-10-28');
  assert.equal(shortDate('2026-10-28'), '2026-10-28');
  assert.equal(shortDate(''), null);
  assert.equal(shortDate(null), null);
});

test('price block normalization prefers the counts slot and falls back to legacy counts', () => {
  const withSlot = normalizePriceBlock({
    listing_avg_price: null, deal_avg_price: 38500, listing_count: null, deal_count: null, snapshot_date: '2026-10-28',
    deal: { price: 38500, month: '2026-10', captured_at: '2026-10-28T02:31:00.000Z', source_url: null, stale: false },
    listing: { price: 40659, month: null, captured_at: '2026-10-28', source_url: null, stale: true },
    counts: { listing_count: 23, deal_count: 5, captured_at: '2026-11-01T09:00:00.000Z' },
  });
  assert.equal(withSlot.deal.month, '2026-10');
  assert.equal(withSlot.deal.capturedDate, '2026-10-28');
  assert.equal(withSlot.listing.stale, true);
  assert.equal(withSlot.counts.listingCount, 23);
  assert.equal(withSlot.counts.capturedAt, '2026-11-01T09:00:00.000Z');
  assert.equal(withSlot.hasCurrentPrice, true);

  // 旧快照: 只有兼容字段, 套数可读但无独立采集时间, 不拿快照日冒充套数时间
  const legacy = normalizePriceBlock({
    listing_avg_price: null, deal_avg_price: 38500, listing_count: 18, deal_count: 3, snapshot_date: '2026-05-08',
  });
  assert.equal(legacy.deal.price, 38500);      // 兼容字段回退成签约条目
  assert.equal(legacy.deal.month, null);       // 旧数据没有所属月份, 不编造
  assert.equal(legacy.deal.capturedDate, '2026-05-08'); // 快照日是唯一可用时间
  assert.equal(legacy.deal.stale, false);      // 陈旧无法判定, 不编造提示
  assert.equal(legacy.counts.listingCount, 18);
  assert.equal(legacy.counts.dealCount, 3);
  assert.equal(legacy.counts.capturedAt, null);
  assert.equal(legacy.hasCurrentPrice, true);

  // 兼容价非正数不算有效价
  const noPrice = normalizePriceBlock({
    listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '',
  });
  assert.equal(noPrice.hasCurrentPrice, false);

  const history = normalizePriceBlock({
    listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '',
    history_deal: { price: 42100, month: '2026-03', captured_at: '2026-03-02', source_url: null, stale: false },
  });
  assert.equal(history.historyDeal.expired, true);
  assert.equal(history.historyDeal.price, 42100);
  assert.equal(history.hasCurrentPrice, false);
});

test('refresh job normalization tolerates missing fields and keeps compat counts', () => {
  const full = normalizeRefreshJob({
    running: false, phase: 'done', mode: 'missing', total: 4, processed: 4,
    updated: 2, noData: 1, failed: 1, skipped: 0, retained: 1,
    result: { outcome: 'partial', published: true, warnings: ['price_snapshots.csv 导出失败（主快照已发布）'] },
  });
  assert.equal(full.updated, 2);
  assert.equal(full.noData, 1);
  assert.deepEqual(full.result.warnings, ['price_snapshots.csv 导出失败（主快照已发布）']);

  const compat = normalizeRefreshJob({ running: true, phase: 'fetching', okCount: 3, errorCount: 1 });
  assert.equal(compat.updated, 3);
  assert.equal(compat.failed, 1);
  assert.equal(compat.noData, 0);
  assert.equal(compat.result, null);

  const cancelled = normalizeRefreshJob({ running: false, phase: 'cancelled', result: null, error: '任务已被终止(数据未改动)' });
  assert.equal(cancelled.phase, 'cancelled');
  assert.equal(cancelled.result, null);
  assert.equal(normalizeRefreshJob(null).running, false);
  assert.equal(normalizeRefreshJob(undefined).phase, 'idle');
});

test('refresh counts stay null when the server did not send them', () => {
  assert.deepEqual(normalizeRefreshCounts({ eligible: 10, missing: 3 }), { eligible: 10, missing: 3 });
  assert.deepEqual(normalizeRefreshCounts({}), { eligible: null, missing: null });
  assert.deepEqual(normalizeRefreshCounts({ eligible: 'x' }), { eligible: null, missing: null });
});

test('a successful start payload becomes a running job so loading and polling start (2026-11-05 regression)', () => {
  // POST 200 data 契约只有 {total, mode, backupFile}: 直接归一化会得到 running=false,
  // loading 与轮询都不启动 —— 必须经 refreshJobFromStartPayload 合成乐观运行态
  const job = refreshJobFromStartPayload({
    total: 12, mode: 'missing', backupFile: 'price_snapshots_2026-11-05.bak.jsonl',
  });
  assert.equal(job.running, true);
  assert.equal(job.phase, 'fetching');
  assert.equal(job.mode, 'missing');
  assert.equal(job.total, 12);
  assert.equal(refreshPhaseText(job), '补齐中 0/12…');
  // 响应若已带真实 running/phase, 以响应为准
  assert.equal(refreshJobFromStartPayload({ total: 1, mode: 'all', phase: 'merging' }).phase, 'merging');
  assert.equal(refreshJobFromStartPayload({ total: 1, mode: 'all', running: false }).running, false);
  // 非法 payload 不崩, 仍按"已启动"处理
  const empty = refreshJobFromStartPayload(null);
  assert.equal(empty.running, true);
  assert.equal(empty.phase, 'fetching');
  assert.equal(empty.total, 0);
});

test('phase text distinguishes the two entries and keeps the four-way accounting', () => {
  assert.equal(
    refreshPhaseText(normalizeRefreshJob({ running: true, phase: 'fetching', mode: 'all', processed: 2, total: 5 })),
    '刷新中 2/5…',
  );
  assert.equal(
    refreshPhaseText(normalizeRefreshJob({ running: true, phase: 'fetching', mode: 'missing', processed: 1, total: 3 })),
    '补齐中 1/3…',
  );
  const done = normalizeRefreshJob({
    running: false, phase: 'done', updated: 2, noData: 1, failed: 1, skipped: 0, retained: 1,
    result: { outcome: 'partial', published: true, warnings: [] },
  });
  assert.equal(refreshPhaseText(done), '部分成功：有效更新 2 · 无数据 1 · 失败 1 · 保留旧价 1');
  const empty = normalizeRefreshJob({ running: false, phase: 'done', result: { outcome: 'succeeded', published: false, warnings: [] } });
  assert.equal(refreshPhaseText(empty), '全部成功');
  assert.equal(refreshPhaseText(normalizeRefreshJob({ running: false, phase: 'cancelled', result: null })), '已停止（数据未改动）');
  assert.equal(refreshPhaseText(normalizeRefreshJob({ running: false, phase: 'error', error: '采集或合并快照失败: x' })), '刷新失败');
  assert.equal(refreshPhaseText(normalizeRefreshJob({ running: false, phase: 'idle' })), null);
  assert.deepEqual(
    refreshSummaryMetrics(normalizeRefreshJob({ updated: 0, noData: 2, failed: 0, skipped: 0, retained: 0 })),
    [{ label: '无数据', value: 2 }],
  );
});

test('per-community status line separates counts updates from price updates', () => {
  assert.equal(
    refreshStatusLine(normalizePriceBlock({ refresh: { outcome: 'updated', price_updated: true, counts_updated: true, partial: false } }).refresh),
    '本轮价格已更新',
  );
  assert.equal(
    refreshStatusLine(normalizePriceBlock({ refresh: { outcome: 'no_data', price_updated: false, counts_updated: true } }).refresh),
    '本轮仅更新套数，价格未更新',
  );
  const failed = { outcome: 'failed', price_updated: false, counts_updated: false, retained: true, retained_reason: 'fetch_failed', retained_price_date: '2026-09-01' };
  assert.equal(
    refreshStatusLine(normalizePriceBlock({ refresh: failed }).refresh),
    '本轮采集失败 · 保留 2026-09-01 价格（抓取失败）',
  );
  const expiredOnly = { outcome: 'no_data', price_updated: false, counts_updated: false, retained: true, retained_reason: 'expired_only', retained_price_date: '2026-08-01' };
  assert.equal(
    refreshStatusLine(normalizePriceBlock({ refresh: expiredOnly }).refresh),
    '本轮无可用价格数据 · 保留 2026-08-01 价格（仅抓到过期价格）',
  );
  assert.equal(
    refreshStatusLine(normalizePriceBlock({ refresh: { outcome: 'skipped' } }).refresh),
    '本轮资格变化，已跳过采集',
  );
  assert.equal(refreshStatusLine(normalizePriceBlock({}).refresh), null);
});

test('dual price lines keep both markets and label the deal month vs listing capture date', () => {
  const block = normalizePriceBlock({
    deal: { price: 38500, month: '2026-10', captured_at: '2026-10-28', source_url: null, stale: false },
    listing: { price: 40659, month: null, captured_at: '2026-10-28', source_url: null, stale: true },
  });
  const [deal, listing] = dualPriceLines(block);
  assert.equal(deal.tag, '签');
  assert.equal(deal.meta, '2026年10月');
  assert.equal(deal.stale, false);
  assert.equal(listing.tag, '挂');
  assert.equal(listing.meta, '2026-10-28');
  assert.equal(listing.stale, true);
  assert.match(listing.title, /超过30天未更新/);
  const missing = dualPriceLines(normalizePriceBlock({}));
  assert.equal(missing[0].missing, true);
  assert.equal(missing[0].text, '—');
});

// ---------- PriceDetails SSR ----------

const dealEntry = { price: 38500, month: '2026-10', captured_at: '2026-10-28T02:31:00.000Z', source_url: 'https://example.com/c/1', stale: false };
const listingEntry = { price: 40659, month: null, captured_at: '2026-10-28', source_url: null, stale: false };
const countsEntry = { listing_count: 23, deal_count: 5, captured_at: '2026-11-01T09:00:00.000Z' };

function renderPrice(price) {
  return renderToStaticMarkup(React.createElement(PriceDetails, { price }));
}

test('the popup shows both prices with their own month and capture date', () => {
  const html = renderPrice({
    listing_avg_price: null, deal_avg_price: 38500, listing_count: null, deal_count: null, snapshot_date: '2026-10-28',
    deal: dealEntry, listing: listingEntry, counts: countsEntry,
  });
  assert.match(html, /签约均价/);
  assert.match(html, /挂牌均价/);
  assert.match(html, /38,500/);
  assert.match(html, /40,659/);
  assert.match(html, /2026年10月签约/);
  assert.match(html, /2026-10-28采集/);
  assert.match(html, /套数采集 2026-11-01/);
  assert.doesNotMatch(html, /超过30天未更新|暂无近期价格/);
});

test('a stale price keeps its value and capture date but carries the 30-day hint', () => {
  const html = renderPrice({
    listing_avg_price: 40659, deal_avg_price: null, listing_count: 23, deal_count: null, snapshot_date: '2026-09-01',
    listing: { ...listingEntry, stale: true },
  });
  assert.match(html, /40,659/);
  assert.match(html, /挂牌价超过30天未更新/);
  assert.match(html, /2026-10-28采集/);
});

test('an expired deal goes to the history area and a price-less community still shows history and counts', () => {
  const html = renderPrice({
    listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '',
    history_deal: { price: 42100, month: '2026-03', captured_at: '2026-03-02', source_url: null, stale: false },
    counts: countsEntry,
  });
  assert.match(html, /暂无近期价格/);
  assert.match(html, /历史参考 2026年3月签约均价 42,100 元\/㎡（2026-03-02采集）/);
  assert.match(html, /超过6个月，不参与当前比价/);
  assert.match(html, /无有效签约价/);
  assert.match(html, /套数采集 2026-11-01/);
});

test('the popup surfaces the per-community refresh outcome without pretending counts are prices', () => {
  const html = renderPrice({
    listing_avg_price: null, deal_avg_price: null, listing_count: null, deal_count: null, snapshot_date: '',
    counts: countsEntry,
    refresh: {
      outcome: 'no_data', partial: false, retained: true, retained_reason: 'expired_only',
      retained_price_date: '2026-08-01', price_updated: false, counts_updated: true,
      price_captured_at: null, counts_captured_at: '2026-11-04T02:00:00.000Z', updated_at: '2026-11-04T02:05:00.000Z',
    },
  });
  assert.match(html, /本轮仅更新套数，价格未更新/);
  assert.match(html, /保留 2026-08-01 价格（仅抓到过期价格）/);
  assert.match(html, /暂无近期价格/);
});

test('legacy snapshots without the new slots still render and never fabricate times', () => {
  // 兼容形状: 只有 deal_avg_price (真实 API 中签/挂互斥), 快照日作为采集日透传
  const html = renderPrice({ listing_avg_price: null, deal_avg_price: 38500, listing_count: 18, deal_count: 3, snapshot_date: '2026-05-08' });
  assert.match(html, /38,500/);
  assert.match(html, /月份未知签约/);      // 旧数据没有所属月份, 如实说明
  assert.match(html, /2026-05-08采集/);    // 快照日是唯一可用时间
  assert.match(html, /18/);
  assert.match(html, /套数无采集时间/);
  assert.doesNotMatch(html, /套数采集 [0-9]/); // 兼容快照没有套数独立时间, 不编造
  assert.doesNotMatch(html, /暂无近期价格/);   // 有兼容价不算缺价
  assert.equal(renderPrice(null).includes('暂无近期价格'), true);
});

// ---------- PriceRefreshControls SSR ----------

function renderControls(props) {
  return renderToStaticMarkup(React.createElement(PriceRefreshControls, {
    job: null, eligible: null, missing: null, notice: null,
    onRefresh() {}, onStop() {},
    ...props,
  }));
}

test('idle controls expose the two entries and disable top-up when nothing is missing', () => {
  const html = renderControls({ eligible: 12, missing: 3 });
  assert.match(html, /刷新已收录/);
  assert.match(html, /补齐价格（3）/);
  assert.doesNotMatch(html, /disabled/);
  assert.match(html, /不受页面搜索与筛选影响/);
  const zero = renderControls({ eligible: 12, missing: 0 });
  assert.match(zero, /补齐价格（0）/);
  assert.match(zero, /disabled/);
  const unknown = renderControls({ eligible: null, missing: null });
  assert.match(unknown, /补齐价格</);
  assert.doesNotMatch(unknown, /disabled/);
});

test('a running job shows progress and the stop control instead of start buttons', () => {
  const running = renderControls({
    job: normalizeRefreshJob({ running: true, phase: 'fetching', mode: 'all', processed: 2, total: 5 }),
    eligible: 5, missing: 1,
  });
  assert.match(running, /刷新中 2\/5…/);
  assert.match(running, /停止/);
  assert.doesNotMatch(running, /刷新已收录|补齐价格/);
  const topUp = renderControls({
    job: normalizeRefreshJob({ running: true, phase: 'fetching', mode: 'missing', processed: 1, total: 3 }),
  });
  assert.match(topUp, /补齐中 1\/3…/);
});

test('a finished round shows the accounting, warnings and reopens both entries', () => {
  const done = renderControls({
    job: normalizeRefreshJob({
      running: false, phase: 'done', total: 4, processed: 4,
      updated: 2, noData: 1, failed: 1, skipped: 0, retained: 1,
      result: { outcome: 'partial', published: true, warnings: ['price_snapshots.csv 导出失败（主快照已发布）'] },
    }),
    eligible: 12, missing: 3,
  });
  assert.match(done, /部分成功：有效更新 2 · 无数据 1 · 失败 1 · 保留旧价 1/);
  assert.match(done, /刷新已收录/);
  assert.match(done, /补齐价格（3）/);
  assert.match(done, /1 条警告/);
  assert.match(done, /主快照已发布/);
  assert.doesNotMatch(done, /跳过/);
});

test('cancel, failure and trigger notices are each stated honestly', () => {
  const cancelled = renderControls({
    job: normalizeRefreshJob({ running: false, phase: 'cancelled', result: null, error: '任务已被终止(数据未改动)' }),
  });
  assert.match(cancelled, /已停止（数据未改动）/);
  const failed = renderControls({
    job: normalizeRefreshJob({ running: false, phase: 'error', error: '采集或合并快照失败: boom' }),
  });
  assert.match(failed, /刷新失败/);
  assert.match(failed, /采集或合并快照失败: boom/);
  assert.match(renderControls({ notice: '没有缺少价格的小区' }), /没有缺少价格的小区/);
  assert.match(renderControls({ notice: '触发刷新失败（409）' }), /触发刷新失败（409）/);
});
