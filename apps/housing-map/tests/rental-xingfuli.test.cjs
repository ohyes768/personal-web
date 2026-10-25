/* eslint-disable @typescript-eslint/no-require-imports -- Node loads local TypeScript for contract tests. */
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
const { safeSourceLink } = require('../src/lib/rental-sources.ts');
const { SourceCandidate } = require('../src/components/rental/RentalSourceManager.tsx');

test('Xingfuli links accept only public Hangzhou rental pages', () => {
  const url = 'https://m.xflapp.com/zufang/hz-7660466810168328198.html';
  assert.equal(safeSourceLink(url), url);
  assert.equal(safeSourceLink('https://m.xflapp.com.evil/zufang/hz-1.html'), undefined);
  assert.equal(safeSourceLink('https://m.xflapp.com/zufang/bj-1.html'), undefined);
  assert.equal(safeSourceLink('https://user@m.xflapp.com/zufang/hz-1.html'), undefined);
});

test('candidate displays the actual rental provider', () => {
  const html = renderToStaticMarkup(React.createElement(SourceCandidate, {
    candidate: { source: 'xingfuli', source_community_id: '6581030816598458638', source_name: '风雅钱塘',
      source_url: 'https://m.xflapp.com/zufang/neighbor-house-list/hz-7502229388495274018.html' },
    busy: false, onConfirm() {}, onReject() {},
  }));
  assert.match(html, /查看幸福里来源/);
  assert.match(html, /https:\/\/m\.xflapp\.com\/zufang\/neighbor-house-list/);
});
