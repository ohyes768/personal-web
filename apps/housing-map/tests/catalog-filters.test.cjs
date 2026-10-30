/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { CatalogTable, CatalogTabs, catalogScope } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
const CatalogFiltersModule = require('../src/components/community/CatalogFilters.tsx');
const { default: CatalogFilters, catalogFilterParams, catalogFilterSummary, catalogFilterScope,
  catalogFiltersForMode, emptyCatalogFilters } = CatalogFiltersModule;

test('admission states contain no rental or auction work', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTabs, {
    summary: { active: true, pipeline: true, admitted: 8, pending: 3, excluded: 5, auction_pending: 99 },
    mode: 'pending', onChange() {},
  }));
  assert.equal((html.match(/<button/g) || []).length, 3);
  assert.doesNotMatch(html, /法拍|租金|99/);
  assert.match(html, /待处理（3）/);
});

test('maintenance splits into its own two tabs and counts pending auctions', () => {
  const { MaintenanceTabs } = require('../src/components/community/DirectoryFlowWorkspace.tsx');
  const summary = { active: true, admitted: 89, excluded: 355, auction_pending: 32 };
  const html = renderToStaticMarkup(React.createElement(MaintenanceTabs, { summary, mode: 'rental', onChange() {} }));
  assert.match(html, /aria-label="维护事项"/);
  assert.match(html, /aria-pressed="true">租金来源/);
  assert.match(html, />法拍待关联（32）</);
  assert.equal((html.match(/<button/g) || []).length, 2);
  const clicks = [];
  const tabs = MaintenanceTabs({ summary, mode: 'rental', onChange: mode => clicks.push(mode) });
  for (const button of tabs.props.children) button.props.onClick();
  assert.deepEqual(clicks, ['rental', 'auctions']);
});

test('pipeline tabs split pending from final exclusions with distinct counts and queries', () => {
  const summary = { active: true, pipeline: true, admitted: 89, pending: 254, excluded: 355, auction_pending: 32 };
  const html = renderToStaticMarkup(React.createElement(CatalogTabs, { summary, mode: 'pending', onChange() {} }));
  assert.match(html, /aria-pressed="true">待处理（254）/);
  assert.match(html, />不收录（101）/);
  assert.match(html, />已收录（89）/);
  assert.doesNotMatch(html, /待处理 \/ 不收录|收录处理状态/);
  assert.deepEqual(catalogScope('pending', true), { state: 'excluded', workflow: 'pending' });
  assert.deepEqual(catalogScope('excluded', true), { state: 'excluded', workflow: 'excluded' });
  assert.deepEqual(catalogScope('admitted', true), { state: 'admitted', workflow: '' });
  const clicks = [];
  const tabs = CatalogTabs({ summary, mode: 'pending', onChange: mode => clicks.push(mode) });
  tabs.props.children.find(button => button.key === 'excluded').props.onClick();
  tabs.props.children.find(button => button.key === 'pending').props.onClick();
  assert.deepEqual(clicks, ['excluded', 'pending']);
  const legacy = renderToStaticMarkup(React.createElement(CatalogTabs, { summary: { ...summary, pipeline: false }, mode: 'excluded', onChange() {} }));
  assert.doesNotMatch(legacy, /待处理/);
  assert.match(legacy, /不收录（355）/);
  assert.deepEqual(catalogScope('excluded', false), { state: 'excluded', workflow: '' });
});

test('pending catalog labels unfinished reasons without calling them exclusions', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, pending: true, busy: false, select() {}, retry() {},
    items: [{ community_id: 'p', community_name: '待确认小区', exclusion_reason: '请确认主体地点', facts_state: 'complete' }] }));
  assert.match(html, /<th>待处理原因 \/ 资料状态<\/th>/);
  assert.match(html, /待核对/);
  assert.doesNotMatch(html, /不收录原因|条件不符/);
});

test('pending rows offer direct exclusion in a dedicated column and preserve row identity', () => {
  const row = { community_id: 'road', community_name: '东信大道', qualification: 'position_review', admission: { revision: 3 } };
  const calls = [];
  const props = { items: [row], excluded: true, pending: true, busy: false, select() {}, retry() {}, exclude: r => calls.push(r) };
  const html = renderToStaticMarkup(React.createElement(CatalogTable, props));
  assert.match(html, /<th>收录决定<\/th>/);
  assert.match(html, /data-label="收录决定"><button[^>]*>确认不收录<\/button>/);
  assert.doesNotMatch(html, /请选择不收录原因|具体原因/);
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'td' && node.props['data-label'] === '收录决定') node.props.children.props.onClick();
    else visit(node.props?.children);
  }
  visit(CatalogTable(props));
  assert.deepEqual(calls, [row]);
  const busy = renderToStaticMarkup(React.createElement(CatalogTable, { ...props, busy: true }));
  assert.match(busy, /disabled=""[^>]*>确认不收录/);
  const virtual = renderToStaticMarkup(React.createElement(CatalogTable, { ...props, items: [{ ...row, source_record_id: 'source-only' }] }));
  assert.doesNotMatch(virtual, />确认不收录</);
  assert.match(virtual, /需先补齐身份/);
});

test('the classification filter offers mode-specific options and preserves selection', () => {
  const render = (mode, value) => renderToStaticMarkup(React.createElement(CatalogFilters, {
    mode, values: { ...emptyCatalogFilters(), [mode === 'admitted' ? 'market' : 'property_type']: value },
    propertyTypes: ['住宅', '商铺'], total: 0, loading: false,
    onChange() {}, onRemove() {}, onClear() {}, onRefresh() {},
  }));
  assert.match(render('admitted', 'new_house'), /value="new_house" selected="">新房/);
  assert.match(render('admitted', ''), />全部房源类型<.*>新房<.*>二手房</);
  const excluded = render('excluded', '住宅');
  assert.match(excluded, />全部来源用途</);
  for (const label of ['住宅', '其他', '写字楼', '商铺', '用途资料缺失']) assert.ok(excluded.includes(label));
  assert.equal((excluded.match(/>住宅</g) || []).length, 1);
});

test('excluded table displays the same TMSF types used by server filtering', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: true, busy: false, select() {}, retry() {},
    items: [{ community_id: '1', community_name: '办公楼', property_types: ['写字楼'], market_state: 'new_house', sources: [], facts_state: 'complete', exclusion_reason: '用途不符' }] }));
  assert.match(html, /写字楼/);
  assert.match(html, /<th>房屋用途<\/th>/);
  assert.match(html, /data-label="房屋用途">写字楼<\/td>/);
  assert.doesNotMatch(html, /新房项目|用途 \/ 市场/);
  assert.doesNotMatch(html, /用途资料缺失/);
});

test('admitted table shows new or second-hand classification without repeating property use', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogTable, { excluded: false, busy: false, select() {}, retry() {},
    items: [
      { community_id: '1', community_name: '测试一', property_types: ['住宅'], market_state: 'new_house' },
      { community_id: '2', community_name: '测试二', property_types: ['住宅'], market_state: 'second_hand' },
      { community_id: '3', community_name: '测试三', property_types: ['住宅'], market_state: 'unknown' },
    ] }));
  assert.match(html, /<th>新房 \/ 二手房<\/th>/);
  assert.match(html, /data-label="新房 \/ 二手房">新房项目<\/td>/);
  assert.match(html, /data-label="新房 \/ 二手房">二手房<\/td>/);
  assert.match(html, /新房 \/ 二手房状态未知/);
  assert.doesNotMatch(html, /住宅|用途 \/ 市场/);
});

test('each catalog tab exposes only the filters that apply to it', () => {
  assert.deepEqual(catalogFilterScope('admitted').primary, ['q', 'district', 'market', 'position']);
  // 收录审核只管用途核对；法拍与租金是数据覆盖度，不进审核筛选。
  assert.deepEqual(catalogFilterScope('admitted').more, ['use']);
  assert.deepEqual(catalogFilterScope('pending').primary, ['q', 'district', 'operation']);
  assert.deepEqual(catalogFilterScope('pending').more, ['use']);
  assert.deepEqual(catalogFilterScope('excluded').primary, ['q', 'district', 'property_type']);
  assert.deepEqual(catalogFilterScope('excluded').more, ['use']);
  // 法拍待关联保留自己的搜索与跳过开关，不套入住宅目录筛选。
  assert.deepEqual(catalogFilterScope('auctions').primary, ['q']);
  assert.deepEqual(catalogFilterScope('auctions').more, []);
});

test('the pending tab filters by pending operation instead of source use or position state', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogFilters, {
    mode: 'pending', values: { ...emptyCatalogFilters(), operation: 'use' }, total: 0, loading: false,
    onChange() {}, onRemove() {}, onClear() {}, onRefresh() {},
  }));
  // 待处理页签按操作三桶筛选，不再暴露来源用途与定位状态。
  assert.match(html, /<span>待处理操作<\/span>/);
  assert.match(html, /value="use" selected="">用途待确认</);
  for (const label of ['全部待处理操作', '地点待处理', '资料待补']) assert.match(html, new RegExp(`>${label}<`));
  assert.match(html, /待处理操作：用途待确认/);
  assert.doesNotMatch(html, /来源用途|定位状态|全部定位/);
});

test('only applicable conditions reach the request', () => {
  const values = { ...emptyCatalogFilters(), q: '鸿雁苑', district: '滨江', market: 'new_house',
    property_type: '住宅', position: 'review', use: 'conflict', operation: 'facts' };
  assert.deepEqual(catalogFilterParams('admitted', values),
    { q: '鸿雁苑', district: '滨江', market: 'new_house', position: 'review', use: 'conflict' });
  assert.deepEqual(catalogFilterParams('pending', values),
    { q: '鸿雁苑', district: '滨江', operation: 'facts', use: 'conflict' });
  assert.deepEqual(catalogFilterParams('excluded', values),
    { q: '鸿雁苑', district: '滨江', property_type: '住宅', use: 'conflict' });
  assert.deepEqual(catalogFilterParams('auctions', values), { q: '鸿雁苑' });
  // 隐藏条件不会因为有值就进入请求。
  const hidden = { ...emptyCatalogFilters(), q: 'x', market: 'new_house' };
  assert.deepEqual(catalogFilterParams('excluded', hidden), { q: 'x' });
});

test('the summary lists exactly the conditions sent to the current tab', () => {
  const values = { ...emptyCatalogFilters(), q: '鸿雁苑', district: '滨江', market: 'new_house',
    property_type: '住宅', position: 'review', use: 'conflict' };
  const admitted = catalogFilterSummary('admitted', values);
  assert.deepEqual(admitted.map(item => item.key), ['q', 'district', 'market', 'position', 'use']);
  assert.equal(admitted.find(item => item.key === 'market').value, '新房');
  assert.equal(admitted.find(item => item.key === 'position').value, '待确认');
  const excluded = catalogFilterSummary('excluded', values);
  assert.deepEqual(excluded.map(item => item.key), ['q', 'district', 'property_type', 'use']);
  // 未知维度不编造分项数量：摘要只有列出的条件。
  assert.equal(excluded.length, 4);
});

test('switching tabs keeps the search and area and clears the tab-specific filters', () => {
  const values = { ...emptyCatalogFilters(), q: '鸿雁苑', district: '滨江', market: 'new_house',
    property_type: '住宅', position: 'review', use: 'conflict', operation: 'use' };
  const next = catalogFiltersForMode(values);
  assert.equal(next.q, '鸿雁苑');
  assert.equal(next.district, '滨江');
  for (const key of ['market', 'property_type', 'position', 'use', 'operation']) assert.equal(next[key], '');
});

test('the filter bar labels every control and counts the folded conditions', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogFilters, {
    mode: 'admitted', values: { ...emptyCatalogFilters(), district: '滨江', use: 'conflict' },
    propertyTypes: ['住宅'], total: 42, loading: false,
    onChange() {}, onRemove() {}, onClear() {}, onRefresh() {},
  }));
  for (const label of ['搜索', '区域', '房源类型', '定位状态']) assert.match(html, new RegExp(`>${label}</span>`));
  assert.match(html, /<summary>更多筛选（1）<\/summary>/);
  assert.match(html, /用途核对/);
  // 收录审核不出现法拍与租金筛选，它们是数据覆盖度不是收录判据。
  assert.doesNotMatch(html, /法拍|租金/);
  assert.match(html, /全部房源类型/); assert.match(html, /全部定位状态/);
  // 生效条件摘要带可移除入口与清空入口。
  assert.match(html, /区域：滨江区/);
  assert.match(html, /用途核对：用途冲突，待人工确认/);
  assert.match(html, /aria-label="移除区域筛选"/);
  assert.match(html, />清空筛选</);
  assert.match(html, /共 42 条/);
});

test('the count states that the list is updating instead of showing a stale total', () => {
  const html = renderToStaticMarkup(React.createElement(CatalogFilters, {
    mode: 'admitted', values: emptyCatalogFilters(), total: 42, loading: true,
    onChange() {}, onRemove() {}, onClear() {}, onRefresh() {},
  }));
  assert.match(html, /更新中/);
  assert.doesNotMatch(html, /共 42 条/);
});

test('removing one summary item clears only that condition and clearing resets every one', () => {
  const removed = [];
  const cleared = [];
  const props = {
    mode: 'admitted', values: { ...emptyCatalogFilters(), district: '滨江', use: 'conflict' },
    total: 3, loading: false,
    onChange() {}, onRemove: key => removed.push(key), onClear: () => cleared.push(true), onRefresh() {},
  };
  const html = renderToStaticMarkup(React.createElement(CatalogFilters, props));
  // 折叠的更多筛选条件仍出现在摘要里，且各自可单独移除。
  assert.match(html, /用途核对：用途冲突，待人工确认/);
  assert.match(html, /区域：滨江区/);
  const buttons = [];
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type === 'button') buttons.push(node);
    visit(node.props?.children);
  }
  visit(CatalogFilters(props));
  const removeRegion = buttons.find(button => button.props['aria-label'] === '移除区域筛选');
  assert.ok(removeRegion, '摘要提供按项移除入口');
  removeRegion.props.onClick();
  assert.deepEqual(removed, ['district']);
  const clearAll = buttons.find(button => button.props.children === '清空筛选');
  assert.ok(clearAll, '摘要提供清空入口');
  clearAll.props.onClick();
  assert.deepEqual(cleared, [true]);
  // 清空后没有生效条件，摘要只剩结果数。
  const empty = renderToStaticMarkup(React.createElement(CatalogFilters, { ...props, values: emptyCatalogFilters() }));
  assert.doesNotMatch(empty, /清空筛选/);
  assert.doesNotMatch(empty, /directory-filter-chip/);
});
