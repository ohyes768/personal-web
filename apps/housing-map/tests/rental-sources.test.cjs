/* eslint-disable @typescript-eslint/no-require-imports -- Node test runner loads local TypeScript. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) {
  require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
  }).outputText, filename);
}
const { SourceCandidate } = require('../src/components/rental/RentalSourceManager.tsx');
const { CollectionControls } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
const { safeSourceLink } = require('../src/lib/rental-sources.ts');
test('candidate exposes evidence and requires confirmation instead of automatic collection', () => {
  const html = renderToStaticMarkup(React.createElement(SourceCandidate, {
    candidate: { source_community_id: '123', source_name: '花园二期', source_url: 'https://zu.fang.com/hz/house-xm123/', source_address: null, evidence: ['分期尚未核对'] },
    busy: false, onConfirm() {}, onReject() {},
  }));
  assert.match(html, /分期尚未核对/); assert.match(html, /确认是这个小区/); assert.match(html, /不是这个小区/);
  assert.match(html, /来源地址：尚不可得/); assert.match(html, /rel="noopener noreferrer"/);
});
test('central rental task exposes missing-source feedback', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, pipeline: true, jobs: {}, action() {},
    errors: { rent: '还没有关联租金来源，请先选择小区并确认来源' },
  }));
  assert.match(html, /采集租金/);
  assert.match(html, /还没有关联租金来源/);
  assert.match(html, /role="alert"/);
});

test('source links reject external domains and credentials', () => {
  assert.equal(safeSourceLink('https://evil.com/hz/'), undefined);
  assert.equal(safeSourceLink('javascript:alert(1)'), undefined);
  assert.equal(safeSourceLink('https://user@zu.fang.com/hz/'), undefined);
  assert.equal(safeSourceLink('https://zu.fang.com/hz/house-xm123/'), 'https://zu.fang.com/hz/house-xm123/');
});
