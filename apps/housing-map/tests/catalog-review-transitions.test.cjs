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
const { CatalogReviewAction } = require('../src/components/community/CatalogReviewAction.tsx');
const { CatalogTable, catalogCanConfirmUse } = require('../src/components/community/DirectoryFlowWorkspace.tsx');

const base = { community_id: 'c', community_name: '测试花园', collection_pipeline_version: 'collection-pipeline-v2',
  admission: { revision: 3, auto_review_locked: false }, qualification: 'eligible', admission_state: 'admitted' };

test('admitted and excluded rows reopen review, manual pending rows complete it', () => {
  for (const state of ['admitted', 'excluded', 'pending']) {
    const row = { ...base, workflow_state: state,
      admission: { ...base.admission, review_requested: state === 'pending' } };
    const calls = [];
    const props = { row, busy: false, action: (kind, target) => calls.push([kind, target]) };
    const node = CatalogReviewAction(props);
    assert.equal(node.type, 'button');
    assert.equal(node.props.children, state === 'pending' ? '完成审核' : '重新审核');
    node.props.onClick();
    assert.deepEqual(calls, [[state === 'pending' ? 'complete-review' : 'reopen-review', row]]);
    assert.match(renderToStaticMarkup(React.createElement(CatalogReviewAction, { ...props, busy: true })), /disabled=""/);
    const html = renderToStaticMarkup(React.createElement(CatalogTable, {
      items: [row], excluded: state !== 'admitted', pending: state === 'pending', busy: false,
      select() {}, review: props.action,
    }));
    assert.match(html, state === 'pending' ? /完成审核/ : /重新审核/);
  }
});

test('ordinary pending, source-only, inactive and legacy rows cannot use new review actions', () => {
  for (const changes of [
    { workflow_state: 'pending' }, { source_record_id: 'virtual' }, { deleted: true },
    { merged_to: 'other' }, { collection_pipeline_version: undefined }, { admission: undefined },
  ]) {
    const row = { ...base, workflow_state: 'admitted', ...changes };
    assert.equal(CatalogReviewAction({ row, busy: false, action() {} }), null);
  }
});

test('a reopened review allows manual use confirmation while an exclusion lock still vetoes it', () => {
  const row = { ...base, workflow_state: 'pending', admission_state: 'excluded', qualification: 'manual_review',
    admission: { revision: 4, auto_review_locked: true, review_requested: true } };
  assert.equal(catalogCanConfirmUse(row), true);
  assert.equal(catalogCanConfirmUse({ ...row, qualification: 'manual_exclusion',
    admission: { ...row.admission, review_requested: false } }), false);
});
