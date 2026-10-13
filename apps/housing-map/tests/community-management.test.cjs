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
const { DirectorySourceCard, ResidentialStateBadge, safeDirectoryLink } = require('../src/components/community/CommunityManagement.tsx');
test('source card preserves original identity, manual method and evidence', () => {
  const html = renderToStaticMarkup(React.createElement(DirectorySourceCard, { item: {
    id: 'r', source: 'fang', source_kind: 'community', source_id: '123', name: '花园一期',
    status: 'matched', method: 'manual', address: '测试路', evidence: ['完整名称一致'], source_url: 'https://zu.fang.com/hz/house-xm123/',
  }}));
  assert.match(html, /花园一期/); assert.match(html, /123/); assert.match(html, /人工关联/); assert.match(html, /完整名称一致/);
  assert.match(html, /noopener noreferrer/);
});
test('directory links reject executable schemes and credentials', () => {
  assert.equal(safeDirectoryLink('javascript:alert(1)'), undefined);
  assert.equal(safeDirectoryLink('https://user:password@example.com'), undefined);
  assert.equal(safeDirectoryLink('https://www.amap.com/'), 'https://www.amap.com/');
});
test('residential badge shows ✅ for residential, ❓ for pending, ❌ for non_residential', () => {
  const cases = [
    ['residential', /✅ 住宅/, 'directory-residential'],
    ['pending', /❓ 待核实/, 'directory-pending'],
    ['non_residential', /❌ 非住宅/, 'directory-non-residential'],
  ];
  for (const [state, contentRe, klass] of cases) {
    const html = renderToStaticMarkup(React.createElement(ResidentialStateBadge, { state }));
    assert.match(html, contentRe);
    assert.match(html, new RegExp(klass));
  }
  const empty = renderToStaticMarkup(React.createElement(ResidentialStateBadge, { state: undefined }));
  assert.match(empty, /—/);
});
