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
const { probeIsRunning, probePath, probeRequest, probeStageLabel } = require('../src/lib/rental-probe.ts');
const { ProbeCandidateCard, XingfuliProbe } = require('../src/components/rental/XingfuliProbe.tsx');
const { RentalSourceAssociation } = require('../src/components/rental/RentalSourceManager.tsx');

const candidate = {
  candidate_id: 'second_hand:6581009489657331972',
  neighborhood_id: '6581009489657331972',
  name: '白金海岸',
  address: '香溢路88号',
  longitude: 120.188369,
  latitude: 30.203001,
  coordinate_system: 'gcj02',
  phase: '',
  rent_total: 31,
  discovered_via: 'second_hand',
  homepage_url: 'https://m.xflapp.com/xiaoqu/hz-6581009489657331972.html',
  evidence: ['完整名称一致', '地址一致'],
  evidence_gaps: [],
  conflicts: [],
  strong: true,
};

test('probe path is scoped to the community', () => {
  assert.equal(probePath('c1'), '/api/map/communities/c1/rental-source/probe');
  assert.equal(probePath('a b'), '/api/map/communities/a%20b/rental-source/probe');
});

test('stage labels distinguish the outcomes', () => {
  assert.match(probeStageLabel('homepage_not_found'), /未找到/);
  assert.match(probeStageLabel('entry_not_found'), /没有可用的租房入口/);
  assert.match(probeStageLabel('bound_pending_collection'), /等待下一轮采集/);
  assert.equal(probeIsRunning('searching_homepage'), true);
  assert.equal(probeIsRunning('resolving_entry'), true);
  assert.equal(probeIsRunning('needs_homepage_selection'), false);
});

test('running probe names the actual API step and terminal states ignore old progress', () => {
  const { probeProgressLabel } = require('../src/lib/rental-probe.ts');
  assert.match(probeProgressLabel({stage:'resolving_entry',current_step:'homepage'}), /小区资料/);
  assert.match(probeProgressLabel({stage:'resolving_entry',current_step:'verified_rental_seed'}), /列表.*归属/);
  assert.equal(probeProgressLabel({stage:'bound_pending_collection',current_step:'verified_rental_seed'}),
    probeStageLabel('bound_pending_collection'));
});

test('probe shows the platform facts and never asks for a link', () => {
  const html = renderToStaticMarkup(React.createElement(ProbeCandidateCard, {
    candidate, busy: false, onSelect() {},
  }));
  assert.match(html, /白金海岸/);
  assert.match(html, /香溢路88号/);
  assert.match(html, /120\.18837/);
  assert.match(html, /完整名称一致/);
  assert.match(html, /选择这个主页/);
  assert.doesNotMatch(html, /neighborhood_id/);
  assert.doesNotMatch(html, /6581009489657331972/);
});

test('a conflicting candidate cannot be chosen', () => {
  const html = renderToStaticMarkup(React.createElement(ProbeCandidateCard, {
    candidate: { ...candidate, name: '白金海岸(南区)', conflicts: ['平台名称带分期标记“南区”，与目录小区不是同一范围'] },
    busy: false, onSelect() {},
  }));
  assert.match(html, /分期标记/);
  assert.match(html, /disabled/);
});

test('probe panel never asks for a link', () => {
  const html = renderToStaticMarkup(React.createElement(XingfuliProbe, {
    communityId: 'c1', onChanged() {},
  }));
  assert.doesNotMatch(html, /粘贴/);
  assert.doesNotMatch(html, /input/);
  assert.doesNotMatch(html, /房天下搜索/);
});

test('source manager offers the probe and no longer asks for a pasted url', () => {
  const html = renderToStaticMarkup(React.createElement(RentalSourceAssociation, {
    communityId: 'c1', onChanged() {},
  }));
  assert.doesNotMatch(html, /房天下小区租房页链接/);
  assert.doesNotMatch(html, /读取链接候选/);
  assert.doesNotMatch(html, /打开房天下搜索/);
  assert.doesNotMatch(html, /复制链接/);
});

test('a failed request shows the reason the backend gave', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: false, json: async () => ({ detail: '候选已更新，请刷新后重新选择' }) });
  try {
    await assert.rejects(() => probeRequest('/api/map/probe'), /候选已更新/);
  } finally {
    global.fetch = original;
  }
});

test('a broken response does not leak a parser error', async () => {
  const original = global.fetch;
  global.fetch = async () => ({ ok: false, json: async () => { throw new Error('Unexpected token <'); } });
  try {
    await assert.rejects(() => probeRequest('/api/map/probe'), /暂时不可用/);
  } finally {
    global.fetch = original;
  }
});

test('legacy refreshed candidate without evidence arrays renders safely and requires retry', () => {
  const legacy = { ...candidate };
  delete legacy.conflicts; delete legacy.evidence; delete legacy.evidence_gaps;
  const html = renderToStaticMarkup(React.createElement(ProbeCandidateCard, {
    candidate: legacy, busy: false, onSelect() { throw new Error('incomplete evidence must not bind'); },
  }));
  assert.match(html, /候选证据不完整，请重试重新探查/);
  assert.match(html, /disabled=""/);
});
