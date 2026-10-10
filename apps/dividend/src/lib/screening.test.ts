import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { DEFAULT_SCREENING, restoreScreeningConditions } from './screening.ts';

const legacy = { min_yield: 4, min_roe: 12, min_roe_avg_3y: 11, exchange: '沪市主板' };
describe('saved screening conditions', () => {
  it('preserves legacy thresholds and supplies the missing decline default', () => {
    assert.deepEqual(restoreScreeningConditions(legacy), { ...legacy, max_quarter_profit_decline_pct: 30 });
  });
  it('restores configured positive thresholds through JSON storage', () => {
    for (const value of [0.1, 20, 30, 50, 100]) {
      const saved = { ...legacy, max_quarter_profit_decline_pct: value };
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
});
