import { describe, expect, it, vi } from 'vitest';
import { runUnpublishBatch } from './batchActions';

describe('batch unpublish', () => {
  it('continues after a member failure and retries only failures', async () => {
    const requests = ['a', 'b', 'c'].map(skillId => ({ skillId, skillName: skillId, target: 'hermes' as const }));
    const action = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('目录冲突')).mockResolvedValueOnce(undefined);
    const results = await runUnpublishBatch(requests, action);
    expect(results.map(r => r.status)).toEqual(['success', 'error', 'success']);
    expect(results[1].error).toBe('目录冲突');
    const retry = vi.fn().mockResolvedValue(undefined);
    await runUnpublishBatch(results.filter(r => r.status === 'error'), retry);
    expect(retry).toHaveBeenCalledTimes(1);
    expect(retry.mock.calls[0][0]).toMatchObject({ skillId: 'b', target: 'hermes' });
  });
});
