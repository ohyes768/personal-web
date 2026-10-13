import { describe, expect, it } from 'vitest';
import {
  addQueueTarget,
  clearQueue,
  removeQueueItem,
  removeQueueTarget,
  queueAfterPublish,
  type QueueEntry,
} from './queue';

describe('queue 纯函数', () => {
  it('keeps failed or blocked targets for retry and removes successful or unchanged targets', () => {
    const initial: QueueEntry[] = [{ skillId: 'a', targets: ['hermes'] }, { skillId: 'b', targets: ['hermes', 'openclaw'] }, { skillId: 'c', targets: ['hermes'] }];
    expect(queueAfterPublish(initial, [
      { skill_id: 'a', target: 'hermes', status: 'success', action: 'add', error: '' },
      { skill_id: 'b', target: 'hermes', status: 'error', action: 'none', error: 'failed' },
    ], [{ skill_id: 'c', target: 'hermes', action: 'unchanged', reason: '', current_revision: '', planned_revision: '' }])).toEqual([
      { skillId: 'b', targets: ['hermes', 'openclaw'] },
    ]);
    expect(initial).toHaveLength(3);
  });
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
