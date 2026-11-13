/**
 * 四挡位「现价落在哪一区 / 会不会触发提醒」单测
 *
 * 口径必须与后端 AlertService._find_hit_level 一致（先卖后买、severity 高者优先），
 * 否则确认卡的提示会骗人。运行：node --experimental-strip-types --test src/lib/valuation.test.ts
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveValuationZone } from './valuation.ts';
import type { AlertLevels } from './types.ts';

function levels(heavy: number, add: number, reduce: number, full: number): AlertLevels {
  return {
    heavy_position: { price: heavy },
    add_position: { price: add },
    reduce_position: { price: reduce },
    full_exit: { price: full },
  };
}

const four = levels(26.58, 30.12, 37.66, 44.30);

test('持有区不命中：现价高于加仓、低于减仓 → 不触发提醒', () => {
  const r = resolveValuationZone(four, 35);
  assert.equal(r.zone, 'hold');
  assert.equal(r.hitKey, null);
  assert.equal(r.willTrigger, false);
  assert.equal(r.hitLabel, null);
});

test('减仓区命中减仓档：现价 ≥ 减仓线 → 该减仓', () => {
  const r = resolveValuationZone(four, 39.96);
  assert.equal(r.zone, 'reduce');
  assert.equal(r.hitKey, 'reduce_position');
  assert.equal(r.hitLabel, '该减仓');
  assert.equal(r.willTrigger, true);
  // 距减仓线 +6.1%
  assert.ok(Math.abs((r.distancePct ?? 0) - 6.106) < 0.01);
});

test('全卖区命中全卖（severity 高于减仓）', () => {
  const r = resolveValuationZone(four, 50);
  assert.equal(r.zone, 'full');
  assert.equal(r.hitKey, 'full_exit');
  assert.equal(r.hitLabel, '全部清仓');
});

test('加仓区命中加仓：现价 ≤ 加仓线', () => {
  const r = resolveValuationZone(four, 28);
  assert.equal(r.zone, 'add');
  assert.equal(r.hitKey, 'add_position');
  assert.equal(r.hitLabel, '加仓价位');
});

test('重仓区命中重仓（severity 高于加仓）：先卖后买里买入侧取高者', () => {
  const r = resolveValuationZone(four, 20);
  assert.equal(r.zone, 'heavy');
  assert.equal(r.hitKey, 'heavy_position');
  assert.equal(r.hitLabel, '可加仓');
});

test('先卖后买：现价同时低于重仓线与高于全卖线不可能，但高位时卖方向优先', () => {
  // 现价高于全卖 → 只命中卖方向
  const r = resolveValuationZone(four, 100);
  assert.equal(r.hitKey, 'full_exit');
});

test('档位不足四条判不出区间（手工配置可能只填一档）', () => {
  const r = resolveValuationZone({ heavy_position: { price: 10 } }, 9);
  assert.equal(r.zone, null);
  assert.equal(r.willTrigger, false);
});

test('缺现价或挡位为空时判不出', () => {
  assert.equal(resolveValuationZone(four, null).zone, null);
  assert.equal(resolveValuationZone(null, 30).zone, null);
  assert.equal(resolveValuationZone(four, 0).zone, null);
});
