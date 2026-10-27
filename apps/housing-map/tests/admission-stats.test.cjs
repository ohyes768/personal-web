/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { formatAdmissionStats } = require('../src/lib/types.ts');

test('admission stats line stays compact and explains hidden reasons on hover', () => {
  const all = formatAdmissionStats({ admitted: 90, displayed: 90, hidden: {} });
  assert.equal(all.line, '收录 90 · 展示 90 · 未展示 0');
  assert.equal(all.title, '');

  const mixed = formatAdmissionStats({ admitted: 90, displayed: 76, hidden: { missing_coordinates: 10, outside_scope: 3, check_coordinates: 1 } });
  assert.equal(mixed.line, '收录 90 · 展示 76 · 未展示 14');
  assert.equal(mixed.title, '缺坐标 10 · 围栏外 3 · 坐标待核 1');

  // 未知状态兜底显示原始值, 不吞掉
  const unknown = formatAdmissionStats({ admitted: 5, displayed: 4, hidden: { new_status_x: 1 } });
  assert.equal(unknown.title, 'new_status_x 1');
});
