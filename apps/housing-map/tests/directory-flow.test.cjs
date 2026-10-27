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

test('collection separates saved evidence outcomes and automatic position followup', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, pipeline: true, action() {}, errors: {}, jobs: {
      tmsf: { running: false, phase: 'succeeded', resolutions: { ready: 4, position_pending: 3, identity_conflict: 2, retryable: 1 },
        position_followup: { state: 'started', targets: 3 },
        evidence_issues: [{ name: '待核对项目', message: '项目身份不一致' }] }
    }
  }));
  assert.match(html, /待地点匹配 3/);
  assert.match(html, /身份待核对 2/);
  assert.match(html, /网络可重试 1/);
  assert.match(html, /已自动衔接主体匹配/);
  assert.match(html, /资料待核对/);
});

test('catalog marks Amap admission address instead of claiming official location', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, {
    items: [{ community_id: 'c', community_name: '测试住宅', address: '月明路1号',
      address_evidence: { origin: 'amap_subject' }, position: { state: 'matched' } }],
    excluded: false, busy: false, select() {}
  }));
  assert.match(html, /高德主体地址/);
});

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

test('Amap offers continuation and current-query retry with the correct request mode', () => {
  const props = { active: true, busy: false, open: true, pipeline: true, errors: {},
    jobs: { amap: { running: false, phase: 'partial_failed', failed: 99, retryable: 2, unqueried: 11 } } };
  const calls = [];
  const tree = CollectionControls({ ...props, action: (...args) => calls.push(args) });
  const buttons = [];
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'button') buttons.push(node);
    visit(node.props?.children);
  }
  visit(tree);
  buttons.find(b => b.props.children === '继续匹配').props.onClick();
  buttons.find(b => Array.isArray(b.props.children) && b.props.children[0] === '重试查询失败（').props.onClick();
  assert.deepEqual(calls, [['/directory/workflow/positions', 'POST', { mode: 'unqueried' }],
    ['/directory/workflow/positions', 'POST', { mode: 'retry_failed' }]]);
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { ...props, action() {} }));
  assert.match(html, /重试查询失败（2）/);
  assert.match(html, /尚未查询 11 条 → 继续匹配/);
  assert.match(html, /查询失败／不完整 2 条 → 重试查询失败/);
  assert.doesNotMatch(html, /重试查询失败（99）/);
  const empty = renderToStaticMarkup(React.createElement(CollectionControls, { ...props,
    jobs: { amap: { retryable: 0 } }, action() {} }));
  assert.match(empty, /disabled=""[^>]*>重试查询失败（0）/);
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

test('position tasks separate normal review and missing places from retryable failures', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { active: true, busy: false, open: true,
    pipeline: true, errors: {}, jobs: { amap: { running: false, phase: 'partial_failed', review: 2, not_found: 1,
      errors: [
        { name: '东冠路710号', state: 'review', message: '未找到唯一可靠位置：候选有歧义、地址不同或结果未完整返回，请核对后确认' },
        { name: '同名小区', state: 'review', message: '找到 2 个同名主体地点，请核对地址并选择' },
        { name: '未找到的小区', state: 'not_found', message: '未找到名称、区域及分类可靠的高德地点' },
        { name: '分页小区', state: 'review', reason: 'results_incomplete', message: '高德结果尚未取完整，请重新查询后确认地点' },
        { name: '异常小区', state: 'error', message: '高德位置查询失败，请重试' },
        { message: '达到本轮请求预算，未完成目标可下次重试' },
      ] } }, action() {} }));
  const sections = html.match(/<details[^>]*>.*?<\/details>/g);
  assert.equal(sections.length, 3);
  assert.match(sections[0], /待人工确认地点（2）/);
  assert.match(sections[0], /东冠路710号：候选地点需人工核对/);
  assert.doesNotMatch(sections[0], /结果未完整返回/);
  assert.match(sections[1], /未找到主体地点（1）/);
  assert.match(sections[2], /查询未完成（可重试）/);
  assert.match(sections[2], /分页小区/);
  assert.match(sections[2], /异常小区/);
  assert.match(sections[2], /达到本轮请求预算/);
  assert.doesNotMatch(sections[2], /东冠路710号|同名小区|未找到的小区/);
});
test('excluded catalog distinguishes insufficient facts from nonresidential conditions', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '资料缺失小区', sources: [], facts_state: 'incomplete', exclusion_reason: '用途资料缺失，待补充' },
      { community_id: '2', community_name: '办公楼', sources: [], facts_state: 'complete', exclusion_reason: '用途为写字楼，不收录' }] }));
  assert.match(html, /资料待补，可重新获取/); assert.match(html, /条件不符/); assert.match(html, /查看资料/);
  assert.doesNotMatch(html, />更新资料<\/button>/);
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
