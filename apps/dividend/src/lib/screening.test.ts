import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  DEFAULT_SCREENING,
  isDefaultScreeningConditions,
  restoreScreeningConditions,
  summarizeChecks,
  type ScreeningCheck,
} from './screening.ts';

const legacy = { min_yield: 4, min_roe: 12, min_roe_avg_3y: 11, exchange: '沪市主板' };
describe('saved screening conditions', () => {
  it('preserves legacy thresholds and supplies the missing decline and CAGR defaults', () => {
    assert.deepEqual(restoreScreeningConditions(legacy), { ...legacy, max_quarter_profit_decline_pct: 30, min_cagr_3y: 0 });
  });
  it('restores configured positive thresholds through JSON storage', () => {
    for (const value of [0.1, 20, 30, 50, 100]) {
      const saved = { ...legacy, max_quarter_profit_decline_pct: value, min_cagr_3y: 0 };
      assert.deepEqual(restoreScreeningConditions(JSON.parse(JSON.stringify(saved))), saved);
    }
  });
  it('rejects malformed explicit thresholds instead of treating them as legacy', () => {
    for (const value of [0, -20, 101, null, undefined, '30', NaN, Infinity]) {
      assert.deepEqual(restoreScreeningConditions({ ...legacy, max_quarter_profit_decline_pct: value }), DEFAULT_SCREENING);
    }
  });
  it('uses defaults for corrupt existing fields and empty storage', () => {
    for (const saved of [null, [], 'invalid', { ...legacy, min_roe: Infinity }, { ...legacy, min_yield: -1 }]) {
      assert.deepEqual(restoreScreeningConditions(saved), DEFAULT_SCREENING);
    }
  });
  it('detects whether the conditions are the built-in defaults', () => {
    assert.equal(isDefaultScreeningConditions(DEFAULT_SCREENING), true);
    assert.equal(isDefaultScreeningConditions({ ...DEFAULT_SCREENING, min_yield: 5 }), false);
    assert.equal(isDefaultScreeningConditions({ ...DEFAULT_SCREENING, min_cagr_3y: 5 }), false);
  });
});

function check(result: ScreeningCheck['result']): ScreeningCheck {
  return { key: 'k', label: 'l', result, value_text: '', threshold_text: '', detail: '', reason: '', warning: '' };
}

describe('screening check summary', () => {
  it('counts every verdict kind', () => {
    const summary = summarizeChecks([check('pass'), check('pass'), check('fail'), check('missing'), check('warn')]);
    assert.deepEqual(summary, { pass: 2, fail: 1, missing: 1, warn: 1, total: 5 });
  });
  it('treats missing input as an empty summary', () => {
    assert.deepEqual(summarizeChecks(null), { pass: 0, fail: 0, missing: 0, warn: 0, total: 0 });
    assert.deepEqual(summarizeChecks([]), { pass: 0, fail: 0, missing: 0, warn: 0, total: 0 });
  });
});
