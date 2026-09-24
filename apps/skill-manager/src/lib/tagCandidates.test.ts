import { describe, expect, it } from 'vitest';
import { getTagCandidates } from './tagCandidates';

describe('getTagCandidates', () => {
  it('shows a newly selected tag on a skill that had no tags', () => {
    expect(getTagCandidates([], [], ['投资'])).toEqual(['投资']);
  });

  it('keeps original tags available after deselection', () => {
    expect(getTagCandidates([], ['旧标签'], [])).toEqual(['旧标签']);
  });
});
