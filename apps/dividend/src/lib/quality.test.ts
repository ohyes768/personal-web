import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  buildQualityQueue,
  dimensionShorthand,
  formatElapsedSince,
  formatElapsedSpan,
  isQualityPending,
  qualityFinishMessage,
  type QualityPerCodeState,
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

describe('buildQualityQueue（运行优先、排队按受理顺序、终态新的在前）', () => {
  const status = (state: QualityPerCodeState, extra: Record<string, unknown> = {}) => ({
    state, error: state === 'failed' ? 'run 失败' : null, updated_at: '2026-10-29T10:00:00+08:00', ...extra,
  });
  it('分区排序：running → queued（按 queued_at）→ terminal（按 finished_at 倒序）', () => {
    const view = buildQualityQueue({
      late: status('queued', { queued_at: '2026-10-29T10:02:00+08:00' }),
      early: status('queued', { queued_at: '2026-10-29T10:01:00+08:00' }),
      runA: status('running', { started_at: '2026-10-29T10:03:00+08:00' }),
      old: status('completed', { finished_at: '2026-10-29T09:00:00+08:00', started_at: '2026-10-29T08:50:00+08:00' }),
      recent: status('failed', { finished_at: '2026-10-29T09:30:00+08:00', started_at: '2026-10-29T09:20:00+08:00' }),
    });
    assert.deepEqual(view.rows.map(row => row.code), ['runA', 'early', 'late', 'recent', 'old']);
    assert.equal(view.runningCount, 1);
    assert.equal(view.queuedCount, 2);
  });
  it('缺时间戳的项不参与时间排序但不丢失', () => {
    const view = buildQualityQueue({ legacy: { state: 'completed', error: null, updated_at: 'x' } });
    assert.equal(view.rows.length, 1);
    assert.equal(view.rows[0].code, 'legacy');
  });
});

describe('isQualityPending', () => {
  it('queued/running 为 pending，completed/failed/缺失不是', () => {
    assert.equal(isQualityPending({ state: 'queued', error: null, updated_at: 'x' }), true);
    assert.equal(isQualityPending({ state: 'running', error: null, updated_at: 'x' }), true);
    assert.equal(isQualityPending({ state: 'completed', error: null, updated_at: 'x' }), false);
    assert.equal(isQualityPending({ state: 'failed', error: 'e', updated_at: 'x' }), false);
    assert.equal(isQualityPending(undefined), false);
  });
});

describe('运行时长计时（R3：从实际开始执行起算，完成后定格）', () => {
  const startedAt = '2026-10-29T10:00:00+08:00';
  it('运行 125 秒显示 2分5秒，且随本地时钟推进', () => {
    const base = new Date('2026-10-29T10:02:05+08:00').getTime();
    assert.equal(formatElapsedSince(startedAt, base), '2分5秒');
    assert.equal(formatElapsedSince(startedAt, base + 1000), '2分6秒');
  });
  it('等待中冒充：queued 缺 started_at 显示未记录', () => {
    assert.equal(formatElapsedSince(null, Date.now()), '未记录');
    assert.equal(formatElapsedSince('garbage', Date.now()), '未记录');
  });
  it('完成后定格 finished-started，缺时间戳显示未记录', () => {
    const finishedAt = '2026-10-29T10:03:35+08:00';
    assert.equal(formatElapsedSpan(startedAt, finishedAt), '3分35秒');
    assert.equal(formatElapsedSpan(null, finishedAt), '未记录');
    assert.equal(formatElapsedSpan(startedAt, null), '未记录');
  });
});
