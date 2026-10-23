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

test('compact badges name the same buckets as the filter labels', () => {
  for (const [review, label] of [[conflict, '待审核'], [{ state: 'checked', result: 'agree_residential' }, '已一致'],
    [{ state: 'not_found', result: 'pending_retry' }, '待复核'], [{ result: 'pending_retry' }, '未复核']]) {
    const html = render(React.createElement(UseReviewBadge, { compact: true, review }));
    assert.ok(html.includes(`>${label}</span>`), `${label} should be shown`);
  }
});

test('excluded rows show the review badge and keep the reason column', () => {
  const html = render(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '风雅钱塘世纪花园', sources: [], facts_state: 'incomplete',
      exclusion_reason: '透明售房网与高德用途分类冲突，待人工审核', use_review: conflict }] }));
  assert.match(html, /<th>高德用途复核<\/th>/); assert.match(html, /待审核/);
  assert.match(html, /分类冲突，待人工审核/); assert.match(html, /资料待补，可重新获取/);
});

test('the panel shows evidence, the conflict and the pending re-review warning', () => {
  const html = render(React.createElement(UseReviewPanel, { review: { ...conflict, re_review: true },
    busy: false, revision: 3, onRecheck() {}, onConfirm() {} }));
  assert.match(html, /<h4>高德用途复核<\/h4>/); assert.match(html, /分类冲突/);
  assert.match(html, /风雅钱塘世纪花园/); assert.match(html, /住宅小区/); assert.match(html, /月明路1076号/);
  assert.match(html, /出现与人工结论相反的证据/);
  assert.match(html, /重新复核/); assert.match(html, /确认用途/);
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
    jobs: { use: { running: false, phase: 'succeeded', processed: 3, total: 3, updated: 1, conflict: 1,
      not_found: 0, uncertain: 1, error: 0, skipped: 0 } }, action() {} }));
  assert.match(html, /复核高德用途/); assert.match(html, /只产生待审核线索/);
  assert.match(html, /已复核 1 · 待审核 1 · 待复核 0 · 匹配不确定 1/);
  const running = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, errors: {},
    jobs: { use: { running: true, phase: 'running', processed: 1, total: 3 } }, action() {} }));
  assert.match(running, /停止用途复核/);
  const legacy = render(React.createElement(CollectionControls, { active: true, busy: false, open: true, errors: {},
    jobs: { use: { running: false, phase: 'succeeded', processed: 2, total: 2, updated: 2, skipped: 0 } }, action() {} }));
  assert.match(legacy, /已处理 2 \/ 2/);
  assert.doesNotMatch(legacy, /待审核 1/);
});
