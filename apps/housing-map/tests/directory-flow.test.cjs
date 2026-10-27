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
const { CollectionControls, CatalogTable, normalizeCollectionJob, workflowRequest } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

test('TMSF collection separates full update and failed-only retry', () => {
  const render = (job, props = {}) => renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, pipeline: true, errors: {}, jobs: { tmsf: job }, action() {}, ...props }));
  const html = render({ running: false, phase: 'partial_failed', retryable: 3 });
  assert.match(html, />更新全部资料<\/button>/);
  assert.match(html, />重试失败项（3）<\/button>/);
  assert.doesNotMatch(html, /disabled=""[^>]*>重试失败项/);
  for (const value of [render({ running: false, phase: 'idle', retryable: 0 }),
                       render({ running: true, phase: 'running', retryable: 3 }),
                       render({ running: false, retryable: 3 }, { active: false }),
                       render({ running: false, retryable: 3 }, { busy: true })]) {
    assert.match(value, /disabled=""[^>]*>重试失败项/);
  }
  assert.match(render({ running: true, phase: 'running', retryable: 3 }), />停止采集<\/button>/);
  const calls = [];
  const tree = CollectionControls({ active: true, busy: false, open: true, pipeline: true,
    jobs: { tmsf: { retryable: 3 } }, errors: {}, action: (...args) => calls.push(args) });
  const buttons = [];
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'button') buttons.push(node);
    visit(node.props?.children);
  }
  visit(tree);
  buttons.find(b => Array.isArray(b.props.children) && b.props.children[0] === '重试失败项（').props.onClick();
  assert.deepEqual(calls, [['/directory/collection', 'POST', { sources: ['tmsf'], mode: 'retry_failed' }]]);
});

test('collection status preserves rental units and nested errors', () => {
  const value = normalizeCollectionJob({ running: false, phase: 'partial_failed', processed_communities: 2,
    total_communities: 5, errors: { total: 1, items: [{ message: '来源未应用关键词' }] } });
  assert.equal(value.processed, 2); assert.equal(value.total, 5);
  assert.equal(value.errors[0].message, '来源未应用关键词');
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { active: true, busy: false, open: true,
    errors: {}, jobs: { rent: value, amap: { running: true, phase: 'running', processed: 1, total: 3 } }, action() {} }));
  assert.match(html, /部分完成.*已处理 2 \/ 5/); assert.match(html, /来源未应用关键词/);
  assert.match(html, /停止补全定位/); assert.match(html, /仅已收录住宅/); assert.doesNotMatch(html, /%/);
});
test('rental task separates actual failures from unqueried communities', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { active: true, busy: false, open: true,
    errors: {}, jobs: { rent: { running: false, phase: 'partial_failed',
      association: { checked: 100, failed: 1, deferred: 99 } } }, action() {} }));
  assert.match(html, /查询失败 1 · 未查询 99/);
  assert.doesNotMatch(html, /查询失败 100/);
});
test('excluded catalog distinguishes insufficient facts from nonresidential conditions', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '资料缺失小区', sources: [], facts_state: 'incomplete', exclusion_reason: '用途资料缺失，待补充' },
      { community_id: '2', community_name: '办公楼', sources: [], facts_state: 'complete', exclusion_reason: '用途为写字楼，不收录' }] }));
  assert.match(html, /资料待补，可重新获取/); assert.match(html, /条件不符/); assert.match(html, /更新资料/);
  assert.doesNotMatch(html, /确认收录|旧主档用途证据初始化/);
});
test('admitted catalog shows asset counts and preserves usable rental data after refresh failure', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '测试花园', district: '滨江', address: '月明路1号',
      coverage: { auction: { property_count: 2, round_count: 4, unidentified_round_count: 1 },
        rental: { state: 'data', sample_count: 12, captured_at: '2026-10-01T00:00:00Z', stale: true, update_failed: true } } },
      { community_id: '2', community_name: '待采集花园', coverage: {
        auction: { property_count: 0, round_count: 0, unidentified_round_count: 0 }, rental: { state: 'pending', sample_count: 0 } } }] }));
  assert.match(html, /<th>法拍<\/th>/); assert.match(html, /<th>租金<\/th>/);
  assert.match(html, /2套/); assert.match(html, /另1轮无法去重/);
  assert.match(html, /有数据 · 12条/); assert.match(html, /更新失败/); assert.match(html, /数据较旧/);
  assert.match(html, /待采集/); assert.match(html, /暂无记录/);
  assert.match(html, /滨江 · 月明路1号/);
  assert.doesNotMatch(html, /<th>区域 \/ 实际地址<\/th>/);
});
test('catalog distinguishes all rental empty states and unknown payloads', () => {
  const states = ['unmapped', 'source_missing', 'no_samples', 'failed'];
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [...states.map((state, i) => ({ community_id: String(i), community_name: state, coverage: {
      auction: { property_count: 0, round_count: 0, unidentified_round_count: 0 }, rental: { state, sample_count: 0 } } })),
      { community_id: 'unknown', community_name: '旧接口未返回覆盖' }] }));
  for (const label of ['待关联来源', '未找到来源', '暂无样本', '采集失败', '状态未知']) assert.match(html, new RegExp(label));
});
test('catalog detail exposes rental date and safe public auction records', () => {
  const { CatalogAuctionRecords, CatalogRentalDetails } = require('../src/components/community/CatalogCoverage.tsx');
  const rental = { state: 'data', sample_count: 1, captured_at: '2026-10-01T00:00:00Z', error: '更新失败，保留旧样本' };
  const html = renderToStaticMarkup(React.createElement(React.Fragment, {},
    React.createElement(CatalogRentalDetails, { value: rental }),
    React.createElement(CatalogAuctionRecords, { coverage: { rental, auction: { property_count: 1, round_count: 2, unidentified_round_count: 1 } },
      records: [{ source: 'laipai', auction_id: 'a', title: '<img onerror=1>', status: 'todo', source_url: 'javascript:alert(1)' },
        { source: 'laipai', auction_id: 'b', asset_id: 'asset', title: '测试房产', status: 'done', source_url: 'https://example.com/auction' }] })));
  assert.match(html, /采集时间：2026\/10\/1/); assert.match(html, /有效样本不足3条/);
  assert.match(html, /更新失败，保留旧样本/); assert.match(html, /&lt;img onerror=1&gt;/);
  assert.match(html, /待开拍/); assert.match(html, /https:\/\/example.com\/auction/);
  assert.doesNotMatch(html, /href="javascript:|<img /);
});
test('request keeps null successes and exposes API conflict instead of claiming success', async () => {
  const previous = global.fetch;
  try {
    global.fetch = async () => ({ ok: true, json: async () => ({ success: true, data: null }) });
    assert.equal(await workflowRequest('/directory/workflow/auctions/a', 'POST', {}), null);
    global.fetch = async () => ({ ok: false, json: async () => ({ detail: '目标已不符合住宅条件' }) });
    await assert.rejects(workflowRequest('/directory/workflow/auctions/a', 'POST', {}), /目标已不符合住宅条件/);
  } finally { global.fetch = previous; }
});
