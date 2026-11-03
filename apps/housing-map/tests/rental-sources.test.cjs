/* eslint-disable @typescript-eslint/no-require-imports -- Node test runner loads local TypeScript. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) {
  require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
  }).outputText, filename);
}
const { RentalSourceAssociation } = require('../src/components/rental/RentalSourceManager.tsx');
const { CollectionControls } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
const { RENTAL_SOURCE_LABEL, safeSourceLink } = require('../src/lib/rental-sources.ts');
test('source manager names the only current provider and offers no candidate confirmation', () => {
  assert.equal(RENTAL_SOURCE_LABEL, '幸福里');
  // The component renders its loading state before the request resolves, so a
  // markup assertion would pass even with retired wording inside. Lock the
  // component source itself instead.
  const source = fs.readFileSync(
    path.join(__dirname, '..', 'src', 'components', 'rental', 'RentalSourceManager.tsx'), 'utf8');
  assert.doesNotMatch(source, /房天下/);
  assert.doesNotMatch(source, /SourceCandidate/);
  assert.doesNotMatch(source, /rental-source\/search/);
  assert.doesNotMatch(source, /method: 'PUT'/);
  assert.doesNotMatch(source, /粘贴|搜索关键词|读取链接候选/);
  const html = renderToStaticMarkup(React.createElement(RentalSourceAssociation, {
    communityId: 'c1', onChanged() {},
  }));
  assert.match(html, /正在加载来源关联/);
});
test('central rental task exposes missing-source feedback', () => {
  const html = renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, pipeline: true, scope: 'maintenance', jobs: {}, action() {},
    errors: { rent: '还没有关联租金来源，请先选择小区并确认来源' },
  }));
  assert.match(html, /采集租金/);
  assert.match(html, /还没有关联租金来源/);
  assert.match(html, /role="alert"/);
});

test('retired Fang hosts are rejected and only public Xingfuli pages are allowed', () => {
  assert.equal(safeSourceLink('https://evil.com/hz/'), undefined);
  assert.equal(safeSourceLink('javascript:alert(1)'), undefined);
  assert.equal(safeSourceLink('https://zu.fang.com/hz/house-xm123/'), undefined);
  assert.equal(safeSourceLink('https://hz.zu.fang.com/hz/house-xm123/'), undefined);
  assert.equal(safeSourceLink('https://user@zu.fang.com/hz/'), undefined);
  assert.equal(safeSourceLink('https://m.xflapp.com/zufang/hz-1.html'), 'https://m.xflapp.com/zufang/hz-1.html');
  assert.equal(safeSourceLink('https://m.xflapp.com:8443/zufang/hz-1.html'), undefined);
  assert.equal(safeSourceLink('http://m.xflapp.com/zufang/hz-1.html'), undefined);
  assert.equal(safeSourceLink('https://m.xflapp.com/zufang/hz-1.html?from=1'), undefined);
});
