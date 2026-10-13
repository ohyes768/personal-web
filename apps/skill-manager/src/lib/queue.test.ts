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
    const initial: QueueEntry[] = [{ skillId: 'a', targets: ['hermes'] }, { skillId: 'b', targets: ['hermes'] }, { skillId: 'c', targets: ['hermes'] }];
    expect(queueAfterPublish(initial, [
      { skill_id: 'a', target: 'hermes', status: 'success', action: 'add', error: '' },
      { skill_id: 'b', target: 'hermes', status: 'error', action: 'none', error: 'failed' },
    ], [{ skill_id: 'c', target: 'hermes', action: 'unchanged', reason: '', current_revision: '', planned_revision: '' }])).toEqual([
      { skillId: 'b', targets: ['hermes'] },
    ]);
    expect(initial).toHaveLength(3);
  });
  it('removing an item from the queue never changes deployment state', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['hermes'], deployment: 'published' },
    ];
    expect(removeQueueItem(initial, 'macro')).toEqual([]);
    expect(initial[0].deployment).toBe('published');
  });

  it('keeps Hermes selection idempotent', () => {
    expect(addQueueTarget([], 'macro', 'hermes')).toEqual([
      { skillId: 'macro', targets: ['hermes'] },
    ]);
    expect(
      addQueueTarget([{ skillId: 'macro', targets: ['hermes'] }], 'macro', 'hermes')[0]
        .targets
    ).toEqual(['hermes']);
  });

  it('clearQueue empties the queue without mutating the input', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['hermes'], deployment: 'published' },
      { skillId: 'news', targets: ['hermes'] },
    ];
    expect(clearQueue(initial)).toEqual([]);
    expect(initial).toHaveLength(2);
  });

  it('removing Hermes leaves no alternate install target', () => {
    const initial: QueueEntry[] = [
      { skillId: 'macro', targets: ['hermes'] },
    ];
    const next = removeQueueTarget(initial, 'macro', 'hermes');
    expect(next).toEqual([]);
    expect(initial[0].targets).toEqual(['hermes']);
  });

  it('removing the last target drops the whole queue item', () => {
    const initial: QueueEntry[] = [{ skillId: 'macro', targets: ['hermes'] }];
    expect(removeQueueTarget(initial, 'macro', 'hermes')).toEqual([]);
  });

  it('addQueueTarget does not duplicate an existing target', () => {
    const initial: QueueEntry[] = [{ skillId: 'macro', targets: ['hermes'] }];
    expect(addQueueTarget(initial, 'macro', 'hermes')[0].targets).toEqual(['hermes']);
  });
});
