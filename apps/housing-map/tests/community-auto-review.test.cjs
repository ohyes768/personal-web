/* eslint-disable @typescript-eslint/no-require-imports -- CommonJS test transform. */
const test = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);

test('automatic report separates suggestions and outcomes with explicit exclusion review', () => {
  const { AutoReport } = require('../src/components/community/AutoReviewPanel.tsx');
  const html = renderToStaticMarkup(React.createElement(AutoReport, { report: {
    snapshot_id: 'snapshot', rule_version: 'v1', counts: { admit: 1, exclude: 1 }, items: [
      { candidate_id: '1', name: '清河花园', action: 'admit', reasons: ['住宅与身份充分'], evidence: [{ source: 'tmsf', property_type: '住宅' }] },
      { candidate_id: '2', name: '写字楼', action: 'exclude', reasons: ['非住宅'], evidence: [] },
    ],
  } }));
  assert.match(html, /建议收录/); assert.match(html, /建议排除/); assert.match(html, /人工确认/);
  assert.match(html, /住宅与身份充分/); assert.match(html, /透明售房网/); assert.match(html, /规则.*v1/);
});

test('management defaults to readonly preview and requires explicit enable', () => {
  const Auto = require('../src/components/community/AutoReviewPanel.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Auto, { onChanged() {} }));
  assert.match(html, /预演/); assert.match(html, /不改变住宅名单/);
  assert.match(html, /明确启用/); assert.match(html, /人工锁/);
});
