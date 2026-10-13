import type { TargetKey } from './queue';

export interface UnpublishItem { skillId: string; skillName: string; target: TargetKey }
export interface UnpublishResult extends UnpublishItem { status: 'success' | 'error'; error?: string }

/** 单项失败不覆盖其他成员结果；调用方以 error 项构造下次重试。 */
export async function runUnpublishBatch(items: UnpublishItem[], action: (item: UnpublishItem) => Promise<unknown>): Promise<UnpublishResult[]> {
  const results: UnpublishResult[] = [];
  for (const item of items) {
    try {
      await action(item);
      results.push({ ...item, status: 'success', error: undefined });
    } catch (error) {
      results.push({ ...item, status: 'error', error: error instanceof Error ? error.message : '下架失败' });
    }
  }
  return results;
}
