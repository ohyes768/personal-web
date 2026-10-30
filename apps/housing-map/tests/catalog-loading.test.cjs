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
function mount(t) {
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
    requests.push({ url, signal: options?.signal });
    const reply = data => ({ ok: true, json: async () => ({ success: true, data }) });
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
    filters: () => nodes(tree, node => node.type?.name === 'CatalogFilters')[0].props,
    next: () => nodes(tree, node => node.type === 'button' && node.props.children === '下一页')[0].props.onClick(),
    async tick() {
      for (const [id, timer] of [...timers]) if (timer.delay === 200) { timers.delete(id); timer.callback(); }
      await new Promise(resolve => setImmediate(resolve));
      render();
    },
  };
}

test('paging and classification filters load directly; search loads while summary is pending', async t => {
  const ui = mount(t);
  const counts = { active: true, pipeline: true, admitted: 80, excluded: 2, auction_pending: 0 };
  ui.render(); await ui.tick();
  assert.equal(ui.summaryReplies.length, 1);
  ui.summaryReplies.shift()(counts); await new Promise(resolve => setImmediate(resolve));
  ui.render(); await ui.tick();
  let summaryCount = ui.requests.filter(r => r.url.includes('/summary?')).length;
  ui.filters().onChange('market', 'new_house'); ui.render(); await ui.tick();
  assert.equal(ui.requests.filter(r => r.url.includes('/summary?')).length, summaryCount);
  assert.match(ui.requests.filter(r => r.url.includes('/catalog?')).at(-1).url, /market=new_house/);
  ui.next(); ui.render(); await ui.tick();
  assert.equal(ui.requests.filter(r => r.url.includes('/summary?')).length, summaryCount);
  assert.match(ui.requests.filter(r => r.url.includes('/catalog?')).at(-1).url, /page=2/);
  ui.filters().onChange('q', '花园'); ui.render(); await ui.tick();
  assert.equal(ui.summaryReplies.length, 1); // deliberately leave slow counts unresolved
  assert.match(ui.requests.filter(r => r.url.includes('/catalog?')).at(-1).url, /page=1/);
  assert.match(decodeURIComponent(ui.requests.filter(r => r.url.includes('/catalog?')).at(-1).url), /q=花园/);
  ui.filters().onRefresh(); ui.render(); await ui.tick();
  assert.equal(ui.requests.filter(r => r.url.includes('/summary?')).length, summaryCount + 2);
});
