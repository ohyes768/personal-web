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

test('collection status preserves rental units and nested errors', () => {
  const value = normalizeCollectionJob({ running: false, phase: 'partial_failed', processed_communities: 2,
    total_communities: 5, errors: { total: 1, items: [{ message: '来源未应用关键词' }] } });
  assert.equal(value.processed, 2); assert.equal(value.total, 5);
  assert.equal(value.errors[0].message, '来源未应用关键词');
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { active: true, busy: false,
    errors: {}, jobs: { rent: value, amap: { running: true, phase: 'running', processed: 1, total: 3 } }, action() {} }));
  assert.match(html, /部分完成.*已处理 2 \/ 5/); assert.match(html, /来源未应用关键词/);
  assert.match(html, /停止补全定位/); assert.match(html, /仅已收录住宅/); assert.doesNotMatch(html, /%/);
});
test('rental task separates actual failures from unqueried communities', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, { active: true, busy: false,
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
test('request keeps null successes and exposes API conflict instead of claiming success', async () => {
  const previous = global.fetch;
  try {
    global.fetch = async () => ({ ok: true, json: async () => ({ success: true, data: null }) });
    assert.equal(await workflowRequest('/directory/workflow/auctions/a', 'POST', {}), null);
    global.fetch = async () => ({ ok: false, json: async () => ({ detail: '目标已不符合住宅条件' }) });
    await assert.rejects(workflowRequest('/directory/workflow/auctions/a', 'POST', {}), /目标已不符合住宅条件/);
  } finally { global.fetch = previous; }
});
