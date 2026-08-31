/**
 * formatTs 必须按北京时间展示。
 * 无测试框架：用 Node 22 strip-types 跑 `node --experimental-strip-types --test <this file>`
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { formatTs } from './runUtils.ts';

describe('formatTs', () => {
  it('把带 +08:00 的 ISO 显示为北京时间', () => {
    assert.equal(formatTs('2026-09-01T16:30:00+08:00'), '2026-09-01 16:30');
  });

  it('把 naive UTC（容器历史）转成北京时间', () => {
    // NAS 容器 UTC 写下的 08:30 = 北京 16:30
    assert.equal(formatTs('2026-08-29T08:30:00'), '2026-08-29 16:30');
  });

  it('把 Zulu UTC 转成北京时间', () => {
    assert.equal(formatTs('2026-08-29T08:30:00Z'), '2026-08-29 16:30');
  });

  it('空值显示为短横', () => {
    assert.equal(formatTs(null), '-');
    assert.equal(formatTs(undefined), '-');
  });
});
