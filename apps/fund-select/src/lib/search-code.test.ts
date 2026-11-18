/**
 * 代码搜索态纯逻辑测试（node --experimental-strip-types）
 * 不 import React，只测归一化与后端参数拼装。
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  SEARCH_CODE_PARAM,
  parseSearchCode,
  searchCodeApiQuery,
  searchCodeToParam,
} from './search-code.ts';

test('参数名固定为 search_code（与后端/URL 契约一致）', () => {
  assert.equal(SEARCH_CODE_PARAM, 'search_code');
});

test('parseSearchCode：标准 6 位通过', () => {
  assert.equal(parseSearchCode('002910'), '002910');
});

test('parseSearchCode：前后空格被 trim', () => {
  assert.equal(parseSearchCode('  003547  '), '003547');
});

test('parseSearchCode：全角数字归一化', () => {
  assert.equal(parseSearchCode('００２９１０'), '002910');
});

test('parseSearchCode：不足/超出 6 位返回 null', () => {
  assert.equal(parseSearchCode('12345'), null);
  assert.equal(parseSearchCode('1234567'), null);
  assert.equal(parseSearchCode(''), null);
});

test('parseSearchCode：缺失/空白返回 null', () => {
  assert.equal(parseSearchCode(null), null);
  assert.equal(parseSearchCode(undefined), null);
  assert.equal(parseSearchCode('   '), null);
});

test('parseSearchCode：含字母/分隔符返回 null（URL 值由机器写，不做宽松解析）', () => {
  assert.equal(parseSearchCode('00000a'), null, '含字母');
  assert.equal(parseSearchCode('002 910'), null, '含空格');
  assert.equal(parseSearchCode('002-910'), null, '含连字符');
});

test('searchCodeToParam：合法写出，非法/空写空串', () => {
  assert.equal(searchCodeToParam('002910'), '002910');
  assert.equal(searchCodeToParam(null), '');
  assert.equal(searchCodeToParam('abc'), '');
});

test('searchCodeApiQuery：只发 code，不带任何阈值参数', () => {
  assert.equal(searchCodeApiQuery('002910'), 'code=002910');
  assert.ok(!searchCodeApiQuery('002910')!.includes('min_'), '搜索不应携带阈值');
});

test('searchCodeApiQuery：非搜索态返回 null（调用方走原筛选拼装）', () => {
  assert.equal(searchCodeApiQuery(null), null);
  assert.equal(searchCodeApiQuery(undefined), null);
  assert.equal(searchCodeApiQuery('abc'), null);
});

// ── buildSearchHref：搜索落点必须保住当前筛选 ──
import { buildSearchHref } from './search-code.ts';

test('buildSearchHref：同页搜索保留当前筛选参数', () => {
  const href = buildSearchHref(
    '/stock?search_code=002910',
    '?min_age=3&min_size_yi=5&max_dd_3y=30',
    '/funds/stock',
  );
  const p = new URLSearchParams(href.split('?')[1]);
  assert.equal(p.get('search_code'), '002910');
  assert.equal(p.get('min_size_yi'), '5', '筛选不能丢（实测踩到的 bug）');
  assert.equal(p.get('max_dd_3y'), '30');
});

test('buildSearchHref：跨页搜索只带 search_code', () => {
  const href = buildSearchHref(
    '/bond?search_code=003547',
    '?min_age=3&min_size_yi=5',
    '/funds/stock',
  );
  const p = new URLSearchParams(href.split('?')[1]);
  assert.equal(href.startsWith('/bond?'), true);
  assert.equal(p.get('search_code'), '003547');
  assert.equal(p.get('min_size_yi'), null, '别的 tab 的筛选不该搬过去');
});

test('buildSearchHref：清掉互斥的 code / focus，page 归 1', () => {
  const href = buildSearchHref(
    '/stock?search_code=002910',
    '?code=159915&focus=1&page=3&min_age=3',
    '/funds/stock',
  );
  const p = new URLSearchParams(href.split('?')[1]);
  assert.equal(p.get('code'), null, 'code= 是直达开抽屉，与搜索态互斥');
  assert.equal(p.get('focus'), null, 'focus=1 已废弃');
  assert.equal(p.get('page'), null, '搜索结果只有 1 条');
  assert.equal(p.get('min_age'), '3');
});

test('buildSearchHref：非搜索落点原样返回', () => {
  assert.equal(buildSearchHref('/managers?keyword=x', '?a=1', '/funds/stock'), '/managers?keyword=x');
});

test('buildSearchHref：不含 basePath（basePath 契约）', () => {
  const href = buildSearchHref('/stock?search_code=002910', '', '/funds/stock');
  assert.equal(href.startsWith('/funds'), false, '写 /funds 会变 /funds/funds/...');
});
