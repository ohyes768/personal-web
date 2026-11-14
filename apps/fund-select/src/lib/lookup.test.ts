/**
 * 基金代码查询纯逻辑测试（node --experimental-strip-types）
 * 不 import React / 组件，只测归一化与状态分类。
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  classifyLookup,
  normalizeCode,
  type FundLookup,
} from './lookup.ts';

test('normalizeCode：标准 6 位', () => {
  assert.equal(normalizeCode('002910'), '002910');
});

test('normalizeCode：前后空格被 trim', () => {
  assert.equal(normalizeCode('  002910  '), '002910');
});

test('normalizeCode：全角数字归一化', () => {
  assert.equal(normalizeCode('００２９１０'), '002910');
});

test('normalizeCode：夹杂空格/连字符时可提取', () => {
  assert.equal(normalizeCode('002 910'), '002910');
  assert.equal(normalizeCode('002-910'), '002910');
});

test('normalizeCode：不足/超出 6 位返回 null', () => {
  assert.equal(normalizeCode('12345'), null);
  assert.equal(normalizeCode('1234567'), null);
  assert.equal(normalizeCode(''), null);
});

test('normalizeCode：纯字母返回 null', () => {
  assert.equal(normalizeCode('abcdef'), null);
  assert.equal(normalizeCode('abc123'), null, '只有 3 位数字，不足 6 位');
});

test('normalizeCode：字母混在 6 位数字里仍提取数字', () => {
  // '0029a0' 的纯数字部分是 00290（5 位）→ null
  assert.equal(normalizeCode('0029a0'), null);
  // '0a0291a0' → 00291 0 = 6 位 → 提取
  assert.equal(normalizeCode('0a0291a0'), '002910');
});

function mkLookup(over: Partial<FundLookup> = {}): FundLookup {
  return {
    code: '002910',
    found: true,
    name: '易方达供给改革混合',
    tab: 'discovery-stock',
    market_type: 'stock',
    in_yaml: null,
    path: '/discovery-stock?code=002910',
    ...over,
  };
}

test('classifyLookup：idle / loading 由调用方控制', () => {
  assert.equal(classifyLookup(null, null), 'idle');
});

test('classifyLookup：found', () => {
  assert.equal(classifyLookup(mkLookup(), null), 'found');
});

test('classifyLookup：found=false → not-found', () => {
  assert.equal(classifyLookup(mkLookup({
    found: false, tab: null, path: null, name: null,
  }), null), 'not-found');
});

test('classifyLookup：found=true 但 path 为空 → not-found（防御）', () => {
  assert.equal(classifyLookup(mkLookup({ path: null }), null), 'not-found');
});

test('classifyLookup：error 优先于 result', () => {
  assert.equal(classifyLookup(mkLookup(), '网络错误'), 'error');
});
