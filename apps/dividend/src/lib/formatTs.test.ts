/**
 * formatBeijingTs 必须按北京时间展示挡位监控更新时间。
 * 无测试框架：用 Node 22 strip-types 跑
 * `node --experimental-strip-types --test src/lib/formatTs.test.ts`
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { formatBeijingMdHm, formatBeijingTs } from './formatTs.ts';

describe('formatBeijingTs', () => {
  it('把带 +08:00 的 ISO 显示为北京时间', () => {
    assert.equal(formatBeijingTs('2026-09-01T15:30:00+08:00'), '2026-09-01 15:30');
  });

  it('把 naive UTC（容器历史）转成北京时间', () => {
    // NAS 容器 UTC 写下的 07:30 = 北京 15:30
    assert.equal(formatBeijingTs('2026-09-01T07:30:00'), '2026-09-01 15:30');
  });

  it('把 Zulu UTC 转成北京时间', () => {
    assert.equal(formatBeijingTs('2026-09-01T07:30:00Z'), '2026-09-01 15:30');
  });

  it('空值返回 null', () => {
    assert.equal(formatBeijingTs(null), null);
    assert.equal(formatBeijingTs(undefined), null);
  });
});

describe('formatBeijingMdHm', () => {
  it('挡位监控卡片用 MM-DD HH:mm', () => {
    assert.equal(formatBeijingMdHm('2026-09-01T07:30:00'), '09-01 15:30');
    assert.equal(formatBeijingMdHm('2026-09-01T15:30:00+08:00'), '09-01 15:30');
  });
});
