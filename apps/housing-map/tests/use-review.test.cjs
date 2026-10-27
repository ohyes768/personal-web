/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup: render } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { UseReviewBadge, default: UseReviewPanel, useReviewBucket } = require('../src/components/community/UseReviewPanel.tsx');
const { CatalogTable, CollectionControls } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

const conflict = { state: 'checked', category: 'residential', result: 'conflict', checked_at: '2026-10-23T02:00:00+00:00',
  evidence: { poi_id: 'B1', name: '风雅钱塘世纪花园', typecode: '120302', type_text: '住宅小区', address: '月明路1076号' } };

test('review buckets separate conflicts from agreement and untried rows', () => {
  assert.equal(useReviewBucket(conflict), 'review');
  assert.equal(useReviewBucket({ state: 'checked', result: 'agree_residential' }), 'done');
  assert.equal(useReviewBucket({ state: 'not_found', result: 'pending_retry' }), 'todo');
  assert.equal(useReviewBucket({ result: 'pending_retry' }), 'none');
  assert.equal(useReviewBucket(undefined), 'none');
});

test('automatic skips explain why and preserve manual querying and existing conflicts', () => {
  const review = { state: 'uncertain', result: 'pending_retry', auto_skip_reason: '区域异常：地址标注拱墅区' };
  assert.equal(useReviewBucket(review), 'skipped');
  const badge = render(React.createElement(UseReviewBadge, { compact: true, review }));
  assert.match(badge, /不自动核对/);
  assert.match(badge, /区域异常/);
  const panel = render(React.createElement(UseReviewPanel, { review, busy: false, onRecheck() {}, onConfirm() {} }));
  assert.match(panel, /区域异常/);
  assert.match(panel, /重新查询高德/);
  assert.equal(useReviewBucket({ ...conflict, auto_skip_reason: '明确非住宅' }), 'review');
  assert.equal(useReviewBucket({ state: 'checked', result: 'agree_non_residential', auto_skip_reason: '明确非住宅' }), 'done');
});

test('pipeline collects subject location and type together without a second bulk use search', () => {
  const html = render(React.createElement(CollectionControls, { active: true, pipeline: true,
    busy: false, open: true, errors: {}, jobs: {}, action() {} }));
  assert.match(html, /匹配楼盘地点与类型/);
  assert.match(html, /候选楼盘先确认主体地点/);
  assert.doesNotMatch(html, /<strong>核对住宅用途<\/strong>/);
  const panel = render(React.createElement(UseReviewPanel, { review: conflict, pipeline: true,
    busy: false, onRecheck() {}, onConfirm() {} }));
  assert.match(panel, /核对已选主体类型/);
  assert.doesNotMatch(panel, /重新查询高德/);
});

test('pipeline renders the selected subject type and unfinished admission stage', () => {
  const { default: PositionPanel } = require('../src/components/community/PositionPanel.tsx');
  const html = render(React.createElement(PositionPanel, { busy: false, confirm() {}, onQuery() {}, position: {
    state: 'matched', has_coordinates: true, candidates: [], selected: { source_id: 'P1', name: '测试住宅',
      poi_type: '住宅小区', poi_typecode: '120302', address: '月明路1076号' } } }));
  assert.match(html, /高德主体类型：住宅小区/);
  assert.match(html, /匹配楼盘地点与类型/);
  const row = render(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: 'c', community_name: '测试住宅', sources: [], collection_pipeline_version: 'collection-pipeline-v2',
      workflow_state: 'pending', qualification: 'position_review', facts_state: 'incomplete', exclusion_reason: '请选择主体地点' }] }));
  assert.match(row, /待确认地点/);
});

test('unselected details show available company types as references and allow explicit query', () => {
  const { default: PositionPanel } = require('../src/components/community/PositionPanel.tsx');
  const html = render(React.createElement(PositionPanel, { busy: false, confirm() {}, onQuery() {}, position: {
    state: 'not_found', has_coordinates: true, candidates: [], reference_candidates: [
      { source_id: 'company', name: 'UT斯达康通讯有限公司', poi_type: '公司企业;公司;公司', address: '六和路368号' }] } }));
  assert.match(html, /UT斯达康通讯有限公司/);
  assert.match(html, /公司企业;公司;公司/);
  assert.match(html, /参考/);
  assert.match(html, /匹配楼盘地点与类型/);
  const empty = render(React.createElement(PositionPanel, { busy: false, confirm() {}, onQuery() {}, position: {
    state: 'pending', has_coordinates: true, candidates: [] } }));
  assert.match(empty, /尚未获取高德类型/);
});

test('pending rows using the excluded compatibility state may be manually excluded', () => {
  const { catalogCanExclude } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
  const row = { admission_state: 'excluded', workflow_state: 'pending', qualification: 'type_uncertain',
    admission: { revision: 1 } };
  assert.equal(catalogCanExclude(row), true);
  assert.equal(catalogCanExclude({ ...row, source_record_id: 'unlinked-source' }), false);
  assert.equal(catalogCanExclude({ ...row, qualification: 'manual_exclusion' }), false);
});

test('catalog shows Amap types directly in both lists with candidate and reference context', () => {
  const base = { community_id: '1', community_name: 'UT斯达康', sources: [], property_types: ['其他'] };
  const table = (position, excluded = true) => render(React.createElement(CatalogTable, {
    excluded, busy: false, select() {}, retry() {}, items: [{ ...base, position }] }));
  for (const excluded of [true, false]) {
    const html = table({ state: 'matched', candidates: [], selected: { poi_type: '商务住宅;住宅区;住宅小区' } }, excluded);
    assert.match(html, /<th>高德类型<\/th>/);
    assert.match(html, /data-label="高德类型"><span>商务住宅;住宅区;住宅小区/);
  }
  const reference = table({ state: 'not_found', candidates: [], reference_candidates: [{ poi_type: '公司企业;公司;公司' }] });
  assert.match(reference, /公司企业;公司;公司/);
  assert.match(reference, /相关地点 · 仅供参考/);
  for (const candidates of [[{ poi_type: '住宅小区' }], [{ poi_type: '写字楼' }, { poi_type: '住宅小区' }]]) {
    for (const excluded of [true, false]) {
      const candidate = table({ state: 'review', candidates }, excluded);
      assert.doesNotMatch(candidate, /写字楼|住宅小区/);
      assert.match(candidate, /候选主体 · 待确认/);
    }
  }
  const review = table({ state: 'review', candidates: [] });
  assert.match(review, /data-label="高德类型"><span[^>]*>待确认地点<\/span>/);
  assert.doesNotMatch(review, /类型缺失/);
  assert.match(table(undefined), /data-label="高德类型"><span[^>]*>未查询/);
  assert.match(table({ state: 'error', candidates: [] }), /data-label="高德类型"><span[^>]*>查询失败/);
  assert.match(table({ state: 'not_found', candidates: [] }), /未找到主体地点/);
  const historical = table({ state: 'pending', candidates: [], query_history: {
    state: 'incomplete', checked_at: '2026-10-25T14:29:13Z', message: '历史查询未完成，待重查' } });
  assert.match(historical, /历史查询未完成，待重查/);
  assert.doesNotMatch(historical, />未查询</);
});

test('compact badges name the same buckets as the filter labels', () => {
  for (const [review, label] of [[conflict, '待人工确认'], [{ state: 'checked', result: 'agree_residential' }, '已一致'],
    [{ state: 'not_found', result: 'pending_retry' }, '未取得明确结果'], [{ result: 'pending_retry' }, '尚未核对']]) {
    const html = render(React.createElement(UseReviewBadge, { compact: true, review }));
    assert.ok(html.includes(`>${label}</span>`), `${label} should be shown`);
  }
});

test('excluded rows show the review badge and keep the reason column', () => {
  const html = render(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '风雅钱塘世纪花园', sources: [], facts_state: 'incomplete',
      exclusion_reason: '透明售房网与高德用途分类冲突，待人工审核', use_review: conflict }] }));
  assert.match(html, /<th>住宅用途核对<\/th>/); assert.match(html, /待人工确认/);
  assert.match(html, /分类冲突，待人工审核/); assert.match(html, /资料待补，可重新获取/);
});

test('the panel shows evidence, the conflict and the pending re-review warning', () => {
  const html = render(React.createElement(UseReviewPanel, { review: { ...conflict, re_review: true },
    busy: false, revision: 3, onRecheck() {}, onConfirm() {} }));
  assert.match(html, /<h4>住宅用途核对<\/h4>/); assert.match(html, /用途冲突/);
  assert.match(html, /风雅钱塘世纪花园/); assert.match(html, /住宅小区/); assert.match(html, /月明路1076号/);
  assert.match(html, /出现与人工结论相反的证据/);
  assert.match(html, /重新查询高德/); assert.match(html, /人工确认用途/);
  const incomplete = render(React.createElement(UseReviewPanel, { review: { state: 'uncertain', result: 'pending_retry',
    error: '高德返回结果未完整，匹配不确定，待复核' }, busy: false, onRecheck() {}, onConfirm() {} }));
  assert.match(incomplete, /高德搜索结果未取完整，暂时无法确认匹配地点。/);
  assert.doesNotMatch(incomplete, /待复核/);
});

test('the confirm form requires an evidence link and a reason for non-residential', () => {
  const closed = render(React.createElement(UseReviewPanel, { review: conflict, busy: false, revision: 3,
    onRecheck() {}, onConfirm() {} }));
  assert.doesNotMatch(closed, /证据链接/);
  const open = render(React.createElement(UseReviewPanel, { review: conflict, busy: false, revision: 3, open: true,
    onRecheck() {}, onConfirm() {} }));
  assert.match(open, /证据链接/); assert.match(open, /证据来源/); assert.match(open, /确认理由/);
  assert.match(open, /<button[^>]*disabled=""[^>]*>提交确认/);
  assert.match(open, /克而瑞/); assert.match(open, /房天下/); assert.match(open, /高德/);
});

test('an admitted row keeps the review state but offers no manual confirmation', () => {
  const html = render(React.createElement(UseReviewPanel, { review: { state: 'checked', result: 'agree_residential' },
    busy: false, revision: 1, canConfirm: false, onRecheck() {}, onConfirm() {} }));
  assert.match(html, /已一致/); assert.doesNotMatch(html, /确认用途|证据链接/);
});

test('the human decision and its evidence stay visible after confirming', () => {
  const html = render(React.createElement(UseReviewPanel, { review: { state: 'checked', result: 'conflict',
    human: { decision: 'residential', decided_at: '2026-10-23T03:00:00+00:00', reason: '克而瑞标注为住宅',
      evidence: [{ source: 'kerui', url: 'https://www.cihud.com/x/1', note: '住宅' }] } },
    busy: false, revision: 4, canConfirm: false, onRecheck() {}, onConfirm() {} }));
  assert.match(html, /人工结论：确认住宅/); assert.match(html, /理由：克而瑞标注为住宅/);
  assert.match(html, /https:\/\/www\.cihud\.com\/x\/1/);
});

test('the use review job card reports outcomes by result and falls back to the legacy wording', () => {
  const html = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, errors: {},
    jobs: { use: { running: false, phase: 'succeeded', processed: 10, total: 10, updated: 1, conflict: 1,
      not_found: 7, uncertain: 1, error: 0, skipped: 0,
      errors: [{ name: '测试小区', message: '高德候选用途不一致，匹配不确定，待复核' }] } }, action() {} }));
  assert.match(html, /核对住宅用途/); assert.match(html, /发现冲突后由你确认/);
  assert.match(html, /已完成用途核对 1 · 用途冲突，待人工确认 1 · 未找到高德地点 7 · 高德地点匹配不明确 1/);
  assert.match(html, /高德候选地点的用途分类不一致或缺失，需人工核对。/);
  assert.doesNotMatch(html, /待审核|待复核|已复核|匹配不确定/);
  const running = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, errors: {},
    jobs: { use: { running: true, phase: 'running', processed: 1, total: 3 } }, action() {} }));
  assert.match(running, /停止用途核对/);
  const legacy = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, errors: {},
    jobs: { use: { running: false, phase: 'succeeded', processed: 2, total: 2, updated: 2, skipped: 0 } }, action() {} }));
  assert.match(legacy, /已处理 2 \/ 2/);
  assert.doesNotMatch(legacy, /待人工确认 1/);
});
