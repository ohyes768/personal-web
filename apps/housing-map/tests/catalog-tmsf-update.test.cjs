/* eslint-disable @typescript-eslint/no-require-imports -- Local TypeScript test transform. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const Workspace = require('../src/components/community/DirectoryFlowWorkspace.tsx').default;

// Exercise the component's real effects and handlers without mounting child UIs.
function mount(t, respond) {
  const slots = []; let cursor = 0; let tree;
  const pending = []; const timers = new Map(); let timerId = 0;
  const originals = { useState: React.useState, useRef: React.useRef, useEffect: React.useEffect,
    fetch: global.fetch, setTimeout: global.setTimeout, clearTimeout: global.clearTimeout };
  const requests = []; const summaryReplies = [];
  React.useState = initial => {
    const index = cursor++;
    if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial };
    return [slots[index].value, next => { slots[index].value = typeof next === 'function' ? next(slots[index].value) : next; }];
  };
  React.useRef = initial => { const index = cursor++; return slots[index] ||= { current: initial }; };
  React.useEffect = (effect, deps) => {
    const index = cursor++; const old = slots[index];
    if (!old || deps.some((value, i) => !Object.is(value, old.deps[i]))) {
      pending.push(() => { old?.cleanup?.(); slots[index] = { deps, cleanup: effect() }; });
    }
  };
  global.setTimeout = (callback, delay) => { const id = ++timerId; timers.set(id, { callback, delay }); return id; };
  global.clearTimeout = id => timers.delete(id);
  global.fetch = (url, options) => {
    requests.push({ url, method: options?.method || 'GET', signal: options?.signal });
    const reply = data => ({ ok: true, json: async () => ({ success: true, data }) });
    if (respond) return respond(url, options, reply);
    if (url.includes('/summary?')) return new Promise(resolve => summaryReplies.push(data => resolve(reply(data))));
    if (url.includes('/catalog?')) return Promise.resolve(reply({ items: [], total: 80 }));
    return Promise.resolve(reply(null));
  };
  const onChanged = () => {};
  function render() {
    cursor = 0; tree = Workspace({ onChanged });
    pending.splice(0).forEach(effect => effect());
    return tree;
  }
  function nodes(node, predicate) {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(child => nodes(child, predicate));
    return [...(predicate(node) ? [node] : []), ...nodes(node.props?.children, predicate)];
  }
  t.after(() => {
    slots.forEach(slot => slot?.cleanup?.());
    Object.assign(React, { useState: originals.useState, useRef: originals.useRef, useEffect: originals.useEffect });
    Object.assign(global, { fetch: originals.fetch, setTimeout: originals.setTimeout, clearTimeout: originals.clearTimeout });
  });
  return { render, requests, summaryReplies,
    node: name => nodes(tree, node => node.type?.name === name)[0],
    filters: () => nodes(tree, node => node.type?.name === 'CatalogFilters')[0].props,
    next: () => nodes(tree, node => node.type === 'button' && node.props.children === '下一页')[0].props.onClick(),
    async tick() {
      for (const [id, timer] of [...timers]) if (timer.delay === 200) { timers.delete(id); timer.callback(); }
      await new Promise(resolve => setImmediate(resolve));
      render();
    },
  };
}

test('single community TMSF refresh keeps details open and reloads evidence and position', async t => {
  const row = { community_id: 'tmsf:123', community_name: '万科城市之光', admission_state: 'admitted',
    sources: [{ id: 't1', source: 'tmsf', status: 'matched' }] };
  let updated = false;
  const ui = mount(t, (url, options, reply) => {
    if (url.includes('/summary?')) return Promise.resolve(reply({ active: true, admitted: 1 }));
    if (url.includes('/catalog?')) return Promise.resolve(reply({ items: [row], total: 1 }));
    if (url.endsWith('/retry')) { updated = true; return Promise.resolve(reply({ community_id: 'formal-id', errors: ['新房项目更新失败，保留已有证据'] })); }
    if (url.endsWith('/position')) return Promise.resolve(reply({ state: 'matched', revision: 2 }));
    if (url.endsWith('/catalog/tmsf%3A123')) return Promise.resolve(reply({ ...row, address: updated ? '更新后的地址' : '原地址' }));
    if (url.endsWith('/catalog/formal-id')) return Promise.resolve(reply({ ...row, community_id: 'formal-id', address: '更新后的地址' }));
    return Promise.resolve(reply(null));
  });
  ui.render(); await ui.tick(); ui.render(); await ui.tick();
  await ui.node('CatalogTable').props.select(row);
  await new Promise(resolve => setImmediate(resolve)); ui.render();
  ui.node('CatalogTmsfDetails').props.onUpdate(); ui.render();
  assert.equal(ui.node('CatalogTmsfDetails').props.updating, true);
  await new Promise(resolve => setImmediate(resolve)); ui.render();
  assert.equal(ui.node('CatalogTmsfDetails').props.updating, false);
  assert.equal(ui.node('DirectoryDialog').props.title, '万科城市之光');
  assert.equal(ui.node('PositionPanel').props.position.revision, 2);
  assert.ok(ui.requests.some(r => r.url.endsWith('/catalog/tmsf%3A123/retry') && r.method === 'POST'));
  assert.ok(ui.requests.some(r => r.url.endsWith('/catalog/formal-id/position') && r.method === 'GET'));
  assert.ok(!ui.requests.some(r => r.url.endsWith('/position/query')));
  const html = require('react-dom/server').renderToStaticMarkup(ui.render());
  assert.match(html, /更新后的地址/);
  assert.match(html, /透明售房网资料部分更新/);
});
