/* eslint-disable @typescript-eslint/no-require-imports -- Local TypeScript test transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS }
}).outputText, filename);

test('cached pages isolate tabs and filters, expire and invalidate after a decision', () => {
  const { WorkspacePageCache } = require('../src/components/community/WorkspacePageCache.ts');
  let time = 0;
  const cache = new WorkspacePageCache(2, 60_000, () => time);
  const first = { items: ['住宅甲'], total: 1 };
  cache.set('/communities?source=tmsf', first);
  assert.equal(cache.get('/communities?source=tmsf'), first);
  assert.equal(cache.get('/reviews?source=tmsf'), undefined);
  assert.equal(cache.get('/communities?source=amap'), undefined);
  time = 60_001;
  assert.equal(cache.get('/communities?source=tmsf'), undefined);
  cache.set('a', first); cache.set('b', first); cache.set('c', first);
  assert.equal(cache.get('a'), undefined);
  cache.clear(); assert.equal(cache.get('c'), undefined);
});
