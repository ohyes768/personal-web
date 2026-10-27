import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  dimensionShorthand,
  qualityFinishMessage,
  qualityJobActive,
  starBadgeClass,
  starsFor,
} from './quality.ts';

describe('starsFor（与 SKILL.md / 后端映射一致）', () => {
  it('边界换挡', () => {
    assert.equal(starsFor(5), 5);
    assert.equal(starsFor(4.5), 5);
    assert.equal(starsFor(4.49), 4);
    assert.equal(starsFor(4.0), 4);
    assert.equal(starsFor(3.99), 3);
    assert.equal(starsFor(3.0), 3);
    assert.equal(starsFor(2.99), 2);
    assert.equal(starsFor(2.0), 2);
    assert.equal(starsFor(1.99), 1);
  });
});

describe('dimensionShorthand', () => {
  it('固定顺序五维简写', () => {
    assert.equal(dimensionShorthand({ business: 4, moat: 5, industry: 3, management: 3, financial: 5 }), '4/5/3/3/5');
  });
  it('缺维度返回 null（显示待分析）', () => {
    assert.equal(dimensionShorthand(undefined), null);
    assert.equal(dimensionShorthand({ business: 4, moat: 5, industry: 3, management: 3, financial: NaN }), null);
  });
  it('维度为 null（未评级）返回 null', () => {
    assert.equal(dimensionShorthand({ business: 3, moat: 4, industry: 3, management: 2, financial: null }), null);
  });
});

describe('starBadgeClass', () => {
  it('5-4 绿、3 琥珀、2-1 红', () => {
    assert.match(starBadgeClass(5), /emerald/);
    assert.match(starBadgeClass(4), /emerald/);
    assert.match(starBadgeClass(3), /amber/);
    assert.match(starBadgeClass(2), /red/);
    assert.match(starBadgeClass(1), /red/);
  });
});

describe('qualityJobActive / qualityFinishMessage', () => {
  const base = { failed_codes: [] as string[], error: null, message: '' };
  it('queued/running 为进行中', () => {
    assert.equal(qualityJobActive({ status: 'queued' }), true);
    assert.equal(qualityJobActive({ status: 'running' }), true);
    assert.equal(qualityJobActive({ status: 'succeeded' }), false);
  });
  it('终态文案', () => {
    assert.match(qualityFinishMessage({ ...base, status: 'succeeded', succeeded: 2 } as never), /成功 2 只/);
    assert.match(qualityFinishMessage({ ...base, status: 'partial_failed', succeeded: 1, failed: 1, failed_codes: ['600000'] } as never), /600000/);
    assert.match(qualityFinishMessage({ ...base, status: 'failed', error: 'boom' } as never), /boom/);
  });
});
