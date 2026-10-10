import { describe, expect, it } from 'vitest';
import { enabledExportTargets, exportTargetLabel, EXPORT_TARGET_ID_PATTERN, LINK_TARGETS, selectedExportTarget } from './targets';

describe('target boundaries', () => {
  it('validates IDs using the HTML Unicode v pattern semantics', () => {
    const pattern = new RegExp(`^(?:${EXPORT_TARGET_ID_PATTERN})$`, 'v');
    expect(pattern.test('laptop-codex')).toBe(true);
    expect(pattern.test('a'.repeat(63))).toBe(true);
    for (const invalid of ['UPPER', '-prefix', 'has space', 'a'.repeat(64), '']) {
      expect(pattern.test(invalid)).toBe(false);
    }
  });
  it('keeps Windows exports out of publishing targets', () => {
    expect(LINK_TARGETS).toEqual(['openclaw', 'hermes']);
    const targets = [{ id: 'laptop', name: '笔记本', install_path: '', notes: '', enabled: true, deployment_count: 1 }, { id: 'tablet', name: '平板', install_path: '', notes: '', enabled: false, deployment_count: 1 }];
    expect(enabledExportTargets(targets).map((item) => item.id)).toEqual(['laptop']);
    expect(selectedExportTarget(targets, 'tablet')).toBe('laptop');
    expect(selectedExportTarget([], 'laptop')).toBe('');
    expect(exportTargetLabel(targets, 'tablet')).toBe('平板');
    expect(exportTargetLabel(targets, 'deleted')).toBe('deleted');
  });
});
