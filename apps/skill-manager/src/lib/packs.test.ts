import { describe, expect, it } from 'vitest';
import { packTargetLabel } from './packs';

describe('pack target availability', () => {
  it('does not report missing repository content as installed', () => {
    expect(packTargetLabel({ source_missing: true, deployments: { hermes: { status: 'active', link_missing: false, verified: true } } } as never, 'hermes')).toBe('源缓存缺失');
  });
  it('distinguishes legacy conversion from direct installation', () => {
    expect(packTargetLabel({ source_missing: false, deployments: { hermes: { status: 'legacy_pending' } } } as never, 'hermes')).toBe('旧安装待转换');
  });
  it('does not present an unverified link as Agent recognition', () => {
    expect(packTargetLabel({ source_missing: false, deployments: { hermes: { status: 'active', link_missing: false, verified: false } } } as never, 'hermes')).toBe('已安装 · Agent 未验证');
  });
});
