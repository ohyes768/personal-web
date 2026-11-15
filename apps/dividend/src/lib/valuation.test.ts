/**
 * 四挡位「现价落在哪一区 / 会不会触发提醒」单测
 *
 * 口径必须与后端 AlertService._find_hit_level 一致（先卖后买、severity 高者优先），
 * 否则确认卡的提示会骗人。运行：node --experimental-strip-types --test src/lib/valuation.test.ts
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  deriveTrackingActions,
  deriveValuationAttempt,
  deriveValuationEvalState,
  resolveValuationZone,
  resolveZoneSteps,
} from './valuation.ts';
import type { FavoriteTrackingDerived, ValuationReportRecord } from './valuation.ts';
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

/* ---------------- resolveZoneSteps：「区间」列的下一步 ---------------- */

test('持有区给两条变盘线：上距减仓、下距加仓', () => {
  const steps = resolveZoneSteps(four, 35);
  assert.equal(steps.length, 2);
  assert.deepEqual(steps.map(s => [s.key, s.direction]), [
    ['reduce_position', 'up'],
    ['add_position', 'down'],
  ]);
  // 都以现价为基准：(37.66-35)/35 = +7.6%，(30.12-35)/35 = -13.9%
  assert.ok(Math.abs(steps[0].pct - 7.6) < 0.05);
  assert.ok(Math.abs(steps[1].pct - 13.94) < 0.05);
});

test('减仓区只盯全卖线（再涨就该全清）', () => {
  const steps = resolveZoneSteps(four, 39.96);
  assert.equal(steps.length, 1);
  assert.equal(steps[0].key, 'full_exit');
  assert.equal(steps[0].direction, 'up');
  // 44.30/39.96-1 = +10.9%
  assert.ok(Math.abs(steps[0].pct - 10.86) < 0.05);
});

test('加仓区向下盯重仓线：跌破就升级为「可加仓」', () => {
  const steps = resolveZoneSteps(four, 28);
  assert.equal(steps.length, 1);
  assert.equal(steps[0].key, 'heavy_position');
  assert.equal(steps[0].direction, 'down');
  // 1 - 26.58/28 = 5.07%
  assert.ok(Math.abs(steps[0].pct - 5.07) < 0.05);
});

test('重仓区向上盯重仓线：涨回线之上就不再是「可加仓」', () => {
  const steps = resolveZoneSteps(four, 20);
  assert.equal(steps.length, 1);
  assert.equal(steps[0].key, 'heavy_position');
  assert.equal(steps[0].direction, 'up');
});

test('全卖区向下盯全卖线：跌回线内降级为「该减仓」', () => {
  const steps = resolveZoneSteps(four, 50);
  assert.equal(steps.length, 1);
  assert.equal(steps[0].key, 'full_exit');
  assert.equal(steps[0].direction, 'down');
  // 1 - 44.30/50 = 11.4%
  assert.ok(Math.abs(steps[0].pct - 11.4) < 0.05);
});

test('正好踩线时距离为 0，且方向仍按所在区给出', () => {
  const steps = resolveZoneSteps(four, 37.66);
  assert.equal(steps[0].pct, 0);
  assert.equal(steps[0].direction, 'up');
});

test('档位/现价不完整时区间列留空（不编造）', () => {
  assert.deepEqual(resolveZoneSteps({ heavy_position: { price: 10 } }, 9), []);
  assert.deepEqual(resolveZoneSteps(four, null), []);
  assert.deepEqual(resolveZoneSteps(null, 30), []);
  assert.deepEqual(resolveZoneSteps(four, 0), []);
});

/* ---------------- deriveValuationEvalState：评估状态（与监控开关无关） ---------------- */

function derived(
  report: { status: string; evaluated_at: string } | null,
  pendingApply = false,
): FavoriteTrackingDerived {
  return {
    state: 'configured',
    pendingApply,
    effective: true,
    report: report as FavoriteTrackingDerived['report'],
  };
}

test('有 ready 报告 → 评估完成', () => {
  const r = deriveValuationEvalState(derived({ status: 'ready', evaluated_at: '2026-11-11T10:00:00' }), null);
  assert.equal(r, 'succeeded');
});

test('ready 报告新于生效挡位 → 待应用（评估完成的子状态）', () => {
  const r = deriveValuationEvalState(derived({ status: 'ready', evaluated_at: '2026-11-11T10:00:00' }, true), null);
  assert.equal(r, 'pending_apply');
});

test('在跑一律评估中（queued/running/cancelling）', () => {
  for (const state of ['queued', 'running', 'cancelling'] as const) {
    assert.equal(deriveValuationEvalState(derived(null), { state }), 'evaluating');
  }
});

test('最近一次失败优先于旧的成功报告：不拿旧报告冒充成功', () => {
  const r = deriveValuationEvalState(
    derived({ status: 'ready', evaluated_at: '2026-01-01T00:00:00' }),
    { state: 'failed', error: 'run 终态 failed' },
  );
  assert.equal(r, 'failed');
});

test('非 ready 报告 → 未出价格', () => {
  for (const status of ['insufficient_data', 'blocked', 'not_applicable'] as const) {
    assert.equal(deriveValuationEvalState(derived({ status, evaluated_at: '2026-11-11T10:00:00' }), null), 'not_ready');
  }
});

test('无报告无任务 → 待评估', () => {
  assert.equal(
    deriveValuationEvalState({ state: 'unevaluated', pendingApply: false, effective: false, report: null }, null),
    'unevaluated',
  );
});

test('有生效挡位但从未走过 Hermes → 手工挡位（不再显示「待评估」）', () => {
  assert.equal(
    deriveValuationEvalState({ state: 'configured' as const, pendingApply: false, effective: true, report: null }, null),
    'manual',
  );
});

/* ---------------- deriveValuationAttempt：最近一次尝试的溯源 ---------------- */

function report(extra: Partial<ValuationReportRecord> = {}): ValuationReportRecord {
  return {
    schema_version: '1', skill_version: '1.2', code: '600004', name: '测试', currency: 'CNY',
    as_of: '2026-11-14', status: 'ready', levels: null, valuation: null, evidence: [],
    data_gaps: [], confidence: null, risks: [], invalidation_conditions: [], summary: '摘要',
    analysis: {}, report_md: '', evaluated_at: '2026-11-14T09:30:00', data_date: null,
    analysis_duration_seconds: 60, run_id: 'run-ok',
    ...extra,
  };
}

test('没有实时条目时退回报告：成功那次的时间/版本/会话都取自报告', () => {
  const attempt = deriveValuationAttempt(report(), null);
  assert.equal(attempt.state, 'completed');
  assert.equal(attempt.at, '2026-11-14T09:30:00');
  assert.equal(attempt.skillVersion, '1.2');
  assert.equal(attempt.runId, 'run-ok');
});

test('从没评估过：state=none，各项为空', () => {
  const attempt = deriveValuationAttempt(null, null);
  assert.equal(attempt.state, 'none');
  assert.equal(attempt.at, null);
  assert.equal(attempt.runId, null);
});

test('失败那次：时间取结束时间、run_id 取失败那次（不退回旧报告）', () => {
  const attempt = deriveValuationAttempt(
    report({ evaluated_at: '2026-11-12T09:00:00', run_id: 'run-old' }),
    { state: 'failed', error: 'run 终态 failed', finished_at: '2026-11-15T10:02:00', run_id: 'run-fail' },
  );
  assert.equal(attempt.state, 'failed');
  assert.equal(attempt.at, '2026-11-15T10:02:00');
  assert.equal(attempt.runId, 'run-fail');
  assert.equal(attempt.error, 'run 终态 failed');
  assert.equal(attempt.skillVersion, null);
});

test('排队中：给队列位次，时间取入队时间', () => {
  const attempt = deriveValuationAttempt(null, {
    state: 'queued', queued_at: '2026-11-15T09:00:00', position: 2, run_id: null,
  });
  assert.equal(attempt.state, 'queued');
  assert.equal(attempt.at, '2026-11-15T09:00:00');
  assert.equal(attempt.position, 2);
});

test('取消：单独成态，时间取结束时间', () => {
  const attempt = deriveValuationAttempt(null, {
    state: 'cancelled', finished_at: '2026-11-15T11:00:00', run_id: 'run-cancel',
  });
  assert.equal(attempt.state, 'cancelled');
  assert.equal(attempt.at, '2026-11-15T11:00:00');
});

test('成功：实时条目与报告同时存在时，run_id 以实时条目为准（同一次尝试）', () => {
  const attempt = deriveValuationAttempt(report({ run_id: 'run-report' }), {
    state: 'completed', run_id: 'run-live', finished_at: '2026-11-14T09:30:00',
  });
  assert.equal(attempt.state, 'completed');
  assert.equal(attempt.runId, 'run-live');
  assert.equal(attempt.skillVersion, '1.2');
});

/* ---------------- deriveTrackingActions：行内动作 ---------------- */

test('从没评估过 → 评估挡位', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(null, null),
    { state: 'unevaluated', pendingApply: false, effective: false, report: null },
  );
  assert.equal(actions.evaluate, 'evaluate');
  assert.equal(actions.apply, false);
  assert.deepEqual(actions.reportLinks, []);
  assert.deepEqual(actions.links, ['settings']);
});

test('最近一次失败 → 重试评估', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(null, { state: 'failed', error: 'x' }),
    { state: 'failed', pendingApply: false, effective: false, report: null },
  );
  assert.equal(actions.evaluate, 'retry');
  assert.equal(actions.apply, false);
});

test('已评估并应用 → 再评估 + 查看报告', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(report(), null),
    { state: 'configured', pendingApply: false, effective: true, report: report() },
  );
  assert.equal(actions.evaluate, 'reevaluate');
  assert.equal(actions.apply, false);
  assert.deepEqual(actions.reportLinks, ['view_report']);
  assert.deepEqual(actions.links, ['settings']);
});

test('有更新的待应用报告 → 应用 + 再评估 + 查看报告', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(report(), null),
    { state: 'pending_apply', pendingApply: true, effective: false, report: report() },
  );
  assert.equal(actions.evaluate, 'reevaluate');
  assert.equal(actions.apply, true);
  assert.deepEqual(actions.reportLinks, ['view_report']);
  assert.deepEqual(actions.links, ['settings']);
});

test('失败与待应用并存：重试与应用同时给出（修正「失败盖住待应用」）', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(report(), { state: 'failed', error: 'boom' }),
    { state: 'failed', pendingApply: true, effective: true, report: report() },
  );
  assert.equal(actions.evaluate, 'retry');
  assert.equal(actions.apply, true);
  assert.deepEqual(actions.reportLinks, ['view_report']);
  assert.deepEqual(actions.links, ['settings']);
});

test('非 ready 报告 → 再评估 + 查看缺口', () => {
  const notReady = report({ status: 'insufficient_data' });
  const actions = deriveTrackingActions(
    deriveValuationAttempt(notReady, null),
    { state: 'not_ready', pendingApply: false, effective: false, report: notReady },
  );
  assert.equal(actions.evaluate, 'reevaluate');
  assert.equal(actions.apply, false);
  assert.deepEqual(actions.reportLinks, ['view_gaps']);
  assert.deepEqual(actions.links, ['settings']);
});

test('评估中：不给评估按钮', () => {
  const actions = deriveTrackingActions(
    deriveValuationAttempt(null, { state: 'running' }),
    { state: 'evaluating', pendingApply: false, effective: false, report: null },
  );
  assert.equal(actions.evaluate, 'running');
  assert.equal(actions.apply, false);
});
