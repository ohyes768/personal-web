import { describe, expect, it } from 'vitest';
import {
  addQueueTarget,
  clearQueue,
  removeQueueItem,
  removeQueueTarget,
  type QueueEntry,
} from './queue';

describe('queue 纯函数', () => {
  it('removing an item from the queue never changes deployment state', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['openclaw'], deployment: 'published' },
    ];
    expect(removeQueueItem(initial, 'macro')).toEqual([]);
    expect(initial[0].deployment).toBe('published');
  });

  it('keeps the two selected targets in one queue item', () => {
    expect(addQueueTarget([], 'macro', 'openclaw')).toEqual([
      { skillId: 'macro', targets: ['openclaw'] },
    ]);
    expect(
      addQueueTarget([{ skillId: 'macro', targets: ['openclaw'] }], 'macro', 'hermes')[0]
        .targets
    ).toEqual(['openclaw', 'hermes']);
  });

  it('clearQueue empties the queue without mutating the input', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['openclaw'], deployment: 'published' },
      { skillId: 'news', targets: ['openclaw', 'hermes'] },
    ];
    expect(clearQueue(initial)).toEqual([]);
    expect(initial).toHaveLength(2);
  });

  it('removing one target keeps the other target in the queue item', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['openclaw', 'hermes'] },
    ];
    const next = removeQueueTarget(initial, 'macro', 'openclaw');
    expect(next[0].targets).toEqual(['hermes']);
    expect(initial[0].targets).toEqual(['openclaw', 'hermes']);
  });

  it('removing the last target drops the whole queue item', () => {
    const initial: QueueEntry[] = [{ skillId: 'macro', targets: ['hermes'] }];
    expect(removeQueueTarget(initial, 'macro', 'hermes')).toEqual([]);
  });

  it('addQueueTarget does not duplicate an existing target', () => {
    const initial: QueueEntry[] = [{ skillId: 'macro', targets: ['openclaw'] }];
    expect(addQueueTarget(initial, 'macro', 'openclaw')[0].targets).toEqual(['openclaw']);
  });
});
