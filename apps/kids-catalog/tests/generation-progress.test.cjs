const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const path = require('node:path');
const file = path.join(__dirname, '../app/generation-progress.ts');
function load() {
  assert.ok(fs.existsSync(file), 'generation status presenter is missing');
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  const mod = {exports: {}};
  new Function('exports', 'module', output)(mod.exports, mod);
  return mod.exports.describeGeneration;
}
test('legacy done does not claim MA ready', () => {
  const s = load()({status:'done'});
  assert.match(s.message,/设备歌单已生成/);
  assert.doesNotMatch(s.message,/MA 已就绪/);
});
test('running distinguishes tags, synchronization and verification', () => {
  const describe=load();
  assert.match(describe({status:'running',integration:{phase:'tagging'}}).message,/音频信息/);
  assert.match(describe({status:'running',integration:{phase:'syncing',ma:{status:'verifying'}}}).message,/核对/);
});
test('ready only from successful backend verification', () => {
  const describe=load();
  assert.equal(describe({status:'done',integration:{ma:{status:'ready'}}}).tone,'success');
  for(const status of ['failed','not_configured']) {
    const result=describe({status:'done',integration:{ma:{status,message:'需要处理'}}});
    assert.equal(result.tone,'warning');
    assert.match(result.message,/需要处理/);
    assert.doesNotMatch(result.message,/MA 已就绪/);
  }
});
