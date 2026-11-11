import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { buildStockSearchParams, normalizeSearchKeyword } from './stock-search.ts';

describe('normalizeSearchKeyword', () => {
  it('trims surrounding whitespace', () => {
    assert.equal(normalizeSearchKeyword('  美的  '), '美的');
    assert.equal(normalizeSearchKeyword('000333'), '000333');
  });

  it('keeps inner spaces and leading zeros untouched', () => {
    assert.equal(normalizeSearchKeyword('  中国 神华 '), '中国 神华');
    assert.equal(normalizeSearchKeyword(' 00333 '), '00333');
  });

  it('treats blank input as no search', () => {
    assert.equal(normalizeSearchKeyword(''), '');
    assert.equal(normalizeSearchKeyword('   '), '');
  });
});

describe('buildStockSearchParams', () => {
  it('sends the trimmed keyword without yield filtering', () => {
    const params = buildStockSearchParams('  美的  ');
    assert.equal(params.search, '美的');
    assert.equal(params.min_yield, 0);
    assert.equal(params.codes, undefined);
  });

  it('narrows the search to favorite codes when codes are given', () => {
    const params = buildStockSearchParams('美的', '000333,600900');
    assert.equal(params.codes, '000333,600900');
    assert.equal(params.search, '美的');
  });

  it('omits codes for an empty scope instead of widening the search', () => {
    const params = buildStockSearchParams('美的', '');
    assert.equal(params.codes, undefined);
    assert.equal(params.search, '美的');
  });

  it('sorts by 3-year average yield descending', () => {
    const params = buildStockSearchParams('美的');
    assert.equal(params.sort_by, 'avg_yield_3y');
    assert.equal(params.sort_order, 'desc');
  });
});
