import { addQueueTarget, type QueueEntry, type TargetKey } from './queue';
import type { SkillCard } from './types';

export interface SkillCollection {
  key: string;
  name: string;
  repository: string | null;
  members: SkillCard[];
  visibleMembers: SkillCard[];
}

export function repositoryKey(repository: string | null): string | null {
  if (!repository) return null;
  try {
    const url = new URL(repository);
    if (url.hostname.toLowerCase() !== 'github.com' || !['https:', 'http:'].includes(url.protocol)) return null;
    const match = url.pathname.replace(/\/+$/, '').replace(/\.git$/i, '').match(/^\/([^/]+)\/([^/]+)$/);
    return match ? `${match[1]}/${match[2]}`.toLowerCase() : null;
  } catch { return null; }
}

export function groupCollections(skills: SkillCard[], visibleSkills: SkillCard[] = skills): SkillCollection[] {
  const visibleIds = new Set(visibleSkills.map(s => s.id));
  const groups = new Map<string, SkillCollection>();
  for (const skill of skills) {
    const repo = skill.source === 'github' ? repositoryKey(skill.repository) : null;
    const key = repo ? `github:${repo}` : `${skill.source}:${skill.id}`;
    let group = groups.get(key);
    if (!group) {
      group = { key, name: repo?.split('/')[1] ?? skill.name, repository: repo, members: [], visibleMembers: [] };
      groups.set(key, group);
    }
    group.members.push(skill);
    if (visibleIds.has(skill.id)) group.visibleMembers.push(skill);
  }
  return [...groups.values()].filter(g => g.visibleMembers.length > 0);
}

export function collectionStats(members: SkillCard[], current: TargetKey = 'hermes') {
  const targets = [current];
  const published: Record<string, number> = {};
  for (const target of targets) {
    published[target] = members.filter(s => s.deployments[target]?.status === 'active' && !s.deployments[target]?.link_missing).length;
  }
  return {
    published,
    abnormal: members.filter(s => s.cache_missing || s.source_missing || targets.some(t => {
      const deployment = s.deployments[t];
      return deployment?.link_missing || (deployment && !['active', 'removed'].includes(deployment.status));
    })).length,
    hasUpdate: members.some(s => s.update?.has_update),
  };
}

export function addCollectionToQueue(queue: QueueEntry[], collection: SkillCollection, target: TargetKey): QueueEntry[] {
  return collection.members.reduce((next, skill) => addQueueTarget(next, skill.id, target), queue);
}
