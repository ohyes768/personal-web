import { describe, expect, it } from 'vitest';
import type { SkillCard } from './types';
import { addCollectionToQueue, collectionStats, groupCollections, repositoryKey } from './collections';

export function skill(id: string, overrides: Partial<SkillCard> = {}): SkillCard {
  return { id, name: id, source: 'github', repository: 'https://github.com/owner/repo',
    path: id, tags: [], summary: '', status: 'active', deployments: {}, update: null,
    cache_missing: false, source_missing: false, ...overrides };
}

describe('repository collections', () => {
  it('normalizes GitHub URLs without mixing owners or malformed addresses', () => {
    expect(repositoryKey('https://github.com/Owner/Repo.git/')).toBe('owner/repo');
    expect(repositoryKey('https://github.com/other/repo')).toBe('other/repo');
    expect(repositoryKey('https://example.com/owner/repo')).toBe(null);
    expect(repositoryKey('https://github.com/owner/repo/tree/main')).toBe(null);
    const groups = groupCollections([skill('a'), skill('b', { repository: 'https://github.com/OWNER/REPO.git' }),
      skill('c', { repository: null }), skill('d', { repository: null })]);
    expect(groups.map(g => g.members.length)).toEqual([2, 1, 1]);
  });
  it('retains all members when only one search result is visible', () => {
    const members = [skill('a'), skill('b')];
    const [group] = groupCollections(members, [members[1]]);
    expect(group.members.map(s => s.id)).toEqual(['a', 'b']);
    expect(group.visibleMembers.map(s => s.id)).toEqual(['b']);
    const queue = addCollectionToQueue([{ skillId: 'other', targets: ['hermes'] }], group, 'hermes');
    expect(queue.map(i => i.skillId)).toEqual(['other', 'a', 'b']);
    expect(addCollectionToQueue(queue, group, 'hermes')).toEqual(queue);
  });
  it('does not count missing links as published and reports blocked members', () => {
    const deployed = { target: 'hermes', status: 'active', revision: '', published_at: '',
      link_target: '', content_hash: '', stale: false, link_missing: false };
    const members = [skill('a', { deployments: { hermes: deployed } }),
      skill('b', { deployments: { hermes: { ...deployed, link_missing: true } } }),
      skill('c', { cache_missing: true })];
    expect(collectionStats(members)).toMatchObject({ published: { hermes: 1 }, abnormal: 2 });
  });
});
