import { describe, expect, it } from 'vitest';
import { EXPORT_TARGETS, LINK_TARGETS, TARGETS } from './targets';

describe('target boundaries', () => {
  it('keeps Windows exports out of publishing targets', () => {
    expect(LINK_TARGETS).toEqual(['openclaw', 'hermes']);
    expect(EXPORT_TARGETS).toEqual(['windows-codex', 'windows-claude']);
    expect(EXPORT_TARGETS.every((key) => TARGETS[key].kind === 'export')).toBe(true);
  });
});
