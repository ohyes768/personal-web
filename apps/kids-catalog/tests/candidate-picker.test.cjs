const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../app/candidate-picker.tsx'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}
}).outputText;
const mod = {exports: {}};
new Function('exports', 'module', 'require', output)(mod.exports, mod, require);
const Picker = mod.exports.default;
const row = {folder: '听，小蜗牛艾玛', title: '听，小蜗牛艾玛', confirmed: false, track_count: 1};
function props(overrides = {}) {
  return {candidates: [row], unchecked: new Set(), disabled: false, confirming: null,
    onToggle() {}, onSetAll() {}, onConfirm() {}, ...overrides};
}
function buttons(node) {
  if (!React.isValidElement(node)) return [];
  return [...(node.type === 'button' ? [node] : []),
    ...React.Children.toArray(node.props.children).flatMap(buttons)];
}
test('remaining one track is visible with an explicit confirmation action', () => {
  const html = renderToStaticMarkup(React.createElement(Picker, props()));
  assert.match(html, /听，小蜗牛艾玛/);
  assert.match(html, /1 首/);
  assert.match(html, /确认保留曲目/);
  let selected;
  const tree = Picker(props({onConfirm(value) {selected = value;}}));
  buttons(tree).find(b => b.props.children === '确认保留曲目').props.onClick();
  assert.equal(selected, row);
});
test('confirmed collections no longer show the confirmation action', () => {
  const tree = Picker(props({candidates: [{...row, confirmed: true}]}));
  assert.ok(!buttons(tree).some(b => b.props.children === '确认保留曲目'));
});
test('generation or pending confirmation disables confirmation buttons', () => {
  for (const state of [{disabled: true}, {confirming: row.folder}]) {
    const action = buttons(Picker(props(state))).find(b => /确认保留曲目|正在核对/.test(b.props.children));
    assert.equal(action.props.disabled, true);
  }
});
