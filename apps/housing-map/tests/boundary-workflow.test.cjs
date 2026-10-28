/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup: render } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(
  ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
  }).outputText, filename);

const {
  BOUNDARY_ERROR_MESSAGES,
  BoundaryWorkflowError,
  boundaryAreaText,
  boundaryErrorText,
  boundaryFootnote,
  boundaryOriginLabel,
  boundaryPhaseLabel,
  boundaryPaths,
  boundaryReferenceSummary,
  isBoundaryJobActive,
  newOperationId,
  runBoundaryAction,
} = require('../src/lib/boundary-workflow.ts');
const {
  BoundaryWorkflowSection,
  BoundaryWorkflowPreview,
} = require('../src/components/community/BoundaryWorkflowPanel.tsx');

const RING = [[[120.207, 30.202], [120.209, 30.202], [120.209, 30.204], [120.207, 30.204], [120.207, 30.202]]];

function candidate(overrides = {}) {
  return {
    candidate_id: 'cand-1',
    job_id: 'job-1',
    community_id: '100',
    community_name: '江汉路小区',
    status: 'ready',
    rings: RING,
    reference_buildings: [{ kind: 'building', rings: RING }],
    area_ha: 3.25,
    building_faces: 4,
    residential_faces: 1,
    low_confidence: false,
    source: 'osm-building',
    warnings: [],
    estimated_at: '2026-10-28T02:00:00Z',
    created_at: '2026-10-28T02:00:00Z',
    revision: 'rev-1',
    stale: false,
    stale_reasons: [],
    applicable: true,
    position: [120.20749, 30.20226],
    ...overrides,
  };
}

function state(overrides = {}) {
  return {
    community_id: '100',
    community_name: '江汉路小区',
    position: [120.20749, 30.20226],
    revision: 'rev-1',
    has_visible_boundary: false,
    boundary_source: null,
    boundary_confirmed_at: null,
    base_has_boundary: false,
    override: null,
    job: null,
    latest_job: null,
    candidate: null,
    revertable: null,
    ...overrides,
  };
}

function view(overrides = {}) {
  return {
    state: state(),
    candidate: null,
    jobPhase: null,
    jobError: null,
    jobErrorCode: null,
    loading: false,
    busy: false,
    error: null,
    ...overrides,
  };
}

const noopActions = {
  startEstimate: async () => {},
  applyCandidate: async () => {},
  rejectCandidate: async () => {},
  revert: async () => {},
};

test('phase labels cover every job phase', () => {
  assert.equal(boundaryPhaseLabel('queued'), '等待处理');
  assert.equal(boundaryPhaseLabel('fetching'), '联网获取建筑');
  assert.equal(boundaryPhaseLabel('estimating'), '估算轮廓');
  assert.equal(boundaryPhaseLabel('failed'), '生成失败');
  assert.equal(boundaryPhaseLabel(null), '未知状态');
});

test('error text distinguishes failure categories and never invents accuracy claims', () => {
  assert.match(boundaryErrorText('timeout'), /超时/);
  assert.match(boundaryErrorText('no_geometry'), /没有可用的建筑数据/);
  assert.match(boundaryErrorText('interrupted'), /中断/);
  assert.equal(boundaryErrorText('unknown_code', '原始提示'), '原始提示');
  assert.equal(boundaryErrorText('unknown_code'), '生成失败,请稍后重试');
  for (const message of Object.values(BOUNDARY_ERROR_MESSAGES)) {
    assert.doesNotMatch(message, /准确率|精度/);
  }
});

test('origin label follows the residential-landuse warning and does not claim a survey', () => {
  const trusted = '采用名称匹配的住宅用地面外轮廓,不是测绘或产权边界';
  assert.equal(boundaryOriginLabel(candidate({ warnings: [trusted], residential_faces: 1 })), '开放街图住宅用地');
  assert.equal(boundaryOriginLabel(candidate({ warnings: ['未匹配到可信住宅用地,轮廓仅按附近建筑聚类估算,需人工确认'] })), '开放街图建筑估算');
  assert.equal(boundaryOriginLabel(candidate({ warnings: [] })), '开放街图建筑估算');
  assert.match(boundaryFootnote(candidate({ warnings: [trusted] })), /不是测绘或产权边界/);
  assert.doesNotMatch(boundaryOriginLabel(candidate({ warnings: [trusted] })), /测绘边界|产权边界/);
});

test('reference summary keeps building faces and residential landuse apart', () => {
  assert.equal(boundaryReferenceSummary(candidate()), '4 个建筑面 + 1 个住宅面');
  assert.equal(boundaryReferenceSummary(candidate({ building_faces: 0, residential_faces: 2 })), '2 个住宅用地面');
  assert.doesNotMatch(boundaryReferenceSummary(candidate()), /楼栋/);
});

test('area text keeps unknown area honest', () => {
  assert.equal(boundaryAreaText(3.256), '3.26 公顷');
  assert.equal(boundaryAreaText(null), '面积未知');
});

test('only in-flight phases count as active', () => {
  assert.equal(isBoundaryJobActive('queued'), true);
  assert.equal(isBoundaryJobActive('estimating'), true);
  assert.equal(isBoundaryJobActive('succeeded'), false);
  assert.equal(isBoundaryJobActive('failed'), false);
  assert.equal(isBoundaryJobActive(null), false);
});

test('api paths keep the /api/map prefix contract', () => {
  assert.equal(boundaryPaths.workflow('100'), '/communities/100/boundary-workflow');
  assert.equal(boundaryPaths.estimates('100'), '/communities/100/boundary-estimates');
  assert.equal(boundaryPaths.job('job-1'), '/boundary-estimates/job-1');
  assert.equal(boundaryPaths.candidate('c1'), '/boundary-candidates/c1');
  assert.equal(boundaryPaths.reject('c1'), '/boundary-candidates/c1/reject');
  assert.equal(boundaryPaths.apply('c1'), '/boundary-candidates/c1/apply');
  assert.equal(boundaryPaths.revert('100'), '/communities/100/boundary-reverts');
});

test('operation ids are unique per operation', () => {
  assert.notEqual(newOperationId(), newOperationId());
});

test('action lifecycle always releases the busy flag', async () => {
  // busy 不复位 -> 界面按钮永远 disabled -> "查看候选"点了没反应(线上踩过)
  const events = [];
  const handlers = {
    busy: () => events.push('busy'),
    settle: error => events.push(`settle:${error}`),
  };
  await runBoundaryAction(async () => {}, handlers);
  assert.deepEqual(events, ['busy', 'settle:null']);

  events.length = 0;
  await runBoundaryAction(async () => { throw new Error('boom'); }, handlers, '生成失败,请稍后重试');
  assert.deepEqual(events, ['busy', 'settle:生成失败,请稍后重试']);
});

test('action lifecycle keeps the server error message when there is one', async () => {
  const seen = [];
  await runBoundaryAction(
    async () => { throw new BoundaryWorkflowError('轮廓已过期,请重新生成', 'candidate_stale', 409); },
    { busy: () => {}, settle: error => seen.push(error) },
    '操作失败,请重试');
  assert.deepEqual(seen, ['轮廓已过期,请重新生成']);
});

test('popup section offers the generate entry when the boundary is missing', () => {
  const html = render(React.createElement(BoundaryWorkflowSection, {
    view: view(),
    actions: noopActions,
    onPreview: () => {},
  }));
  assert.match(html, /暂无地块轮廓/);
  assert.match(html, /生成候选轮廓/);
  assert.doesNotMatch(html, /查看候选/);
});

test('popup section switches to the preview entry once a candidate exists', () => {
  const html = render(React.createElement(BoundaryWorkflowSection, {
    view: view({ candidate: candidate(), state: state({ candidate: { candidate_id: 'cand-1', status: 'ready', area_ha: 3.25, low_confidence: false, created_at: '' } }) }),
    actions: noopActions,
    onPreview: () => {},
  }));
  assert.match(html, /查看候选/);
  assert.doesNotMatch(html, /生成候选轮廓/);
});

test('popup section offers revert only for a manually confirmed boundary', () => {
  const html = render(React.createElement(BoundaryWorkflowSection, {
    view: view({
      state: state({
        has_visible_boundary: true,
        boundary_source: 'osm-building',
        override: { candidate_id: 'cand-1', confirmed_at: '2026-10-28T02:00:00Z', revision: 1, source: 'osm-building' },
        revertable: { operation_id: 'op-1', candidate_id: 'cand-1', confirmed_at: '2026-10-28T02:00:00Z' },
      }),
    }),
    actions: noopActions,
    onPreview: () => {},
  }));
  assert.match(html, /建筑估算 · 人工确认/);
  assert.match(html, /撤销本次应用/);
});

test('popup section surfaces the failure reason and offers a retry', () => {
  // 线上踩过的坑: 任务失败后弹框只显示"联网获取建筑中",失败原因藏在接口里,用户干等
  const html = render(React.createElement(BoundaryWorkflowSection, {
    view: view({
      jobPhase: 'failed',
      jobError: '所有 Overpass 镜像均失败',
      jobErrorCode: 'network',
    }),
    actions: noopActions,
    onPreview: () => {},
  }));
  assert.match(html, /获取建筑数据失败/);
  assert.match(html, /重新生成轮廓/);
  assert.doesNotMatch(html, /联网获取建筑中/);
});

test('preview panel shows the real candidate facts and the decision actions', () => {
  const html = render(React.createElement(BoundaryWorkflowPreview, {
    view: view({ candidate: candidate() }),
    actions: noopActions,
    onBack: () => {},
    onLocate: () => {},
    showReferences: false,
    onToggleReferences: () => {},
  }));
  assert.match(html, /候选轮廓确认/);
  assert.match(html, /3\.25 公顷/);
  assert.match(html, /4 个建筑面 \+ 1 个住宅面/);
  assert.match(html, /开放街图建筑估算/);
  assert.match(html, /不是测绘或产权边界/);
  assert.match(html, /应用此轮廓/);
  assert.match(html, /放弃此候选/);
  assert.match(html, /检查定位/);
  assert.match(html, /重新生成/);
  assert.doesNotMatch(html, /重新获取建筑|范围不合适|去核对定位|更多/);
  assert.doesNotMatch(html, /准确率|置信度\s*\d/);
});

test('preview panel names a residential landuse candidate without calling it a survey', () => {
  const html = render(React.createElement(BoundaryWorkflowPreview, {
    view: view({
      candidate: candidate({
        building_faces: 10,
        residential_faces: 1,
        area_ha: 10.53,
        warnings: ['采用名称匹配的住宅用地面外轮廓,不是测绘或产权边界'],
      }),
    }),
    actions: noopActions,
    onBack: () => {},
    onLocate: () => {},
    showReferences: false,
    onToggleReferences: () => {},
  }));
  assert.match(html, /开放街图住宅用地/);
  assert.match(html, /10 个建筑面 \+ 1 个住宅面/);
  assert.match(html, /10\.53 公顷/);
  assert.match(html, /不是测绘或产权边界/);
  assert.doesNotMatch(html, /测绘成果|产权证/);
});

test('preview panel blocks apply for a stale candidate and explains why', () => {
  const html = render(React.createElement(BoundaryWorkflowPreview, {
    view: view({
      candidate: candidate({ stale: true, stale_reasons: ['基础轮廓或定位已变化'], applicable: false }),
    }),
    actions: noopActions,
    onBack: () => {},
    onLocate: () => {},
    showReferences: true,
    onToggleReferences: () => {},
  }));
  assert.match(html, /候选已过期/);
  assert.match(html, /基础轮廓或定位已变化/);
  assert.match(html, /disabled/);
});

test('preview panel lists quality warnings and the running phase', () => {
  const html = render(React.createElement(BoundaryWorkflowPreview, {
    view: view({
      candidate: candidate({ warnings: ['定位点未落在任何建筑簇内,轮廓取自最近的建筑簇,需人工确认范围'] }),
      jobPhase: 'fetching',
    }),
    actions: noopActions,
    onBack: () => {},
    onLocate: () => {},
    showReferences: false,
    onToggleReferences: () => {},
  }));
  assert.match(html, /联网获取建筑中/);
  assert.match(html, /需人工确认范围/);
});

test('detail tabs put the boundary tab next to the community overview', () => {
  const { default: CommunityDetailTabs } = require('../src/components/community/CommunityDetailTabs.tsx');
  const html = render(React.createElement(CommunityDetailTabs, {
    communityId: '100',
    boundary: React.createElement(BoundaryWorkflowSection, {
      view: view(), actions: noopActions, onPreview: () => {},
    }),
  }, React.createElement('p', null, '概况内容')));
  assert.match(html, /小区概况/);
  assert.match(html, /租金与收益/);
  assert.match(html, /地块轮廓/);
});

test('detail tabs hide the boundary tab when there is nothing to show', () => {
  const { default: CommunityDetailTabs } = require('../src/components/community/CommunityDetailTabs.tsx');
  const html = render(React.createElement(CommunityDetailTabs, {
    communityId: '100',
  }, React.createElement('p', null, '概况内容')));
  assert.match(html, /小区概况/);
  assert.doesNotMatch(html, /地块轮廓/);
});
