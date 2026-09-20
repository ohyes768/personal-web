/**
 * 发布队列纯函数（design 4.2）。
 *
 * 右栏队列是瞬时 UI 状态：加入/移出/清空绝不调用写接口、
 * 绝不修改传入数组（不可变更新），更不影响已部署 Skill。
 */

export type TargetKey = 'openclaw' | 'hermes';

export interface QueueEntry {
  skillId: string;
  targets: TargetKey[];
  /** 卡片携带的部署快照，仅用于展示；队列操作不得改动它 */
  deployment?: string;
}

export function removeQueueItem(items: QueueEntry[], skillId: string): QueueEntry[] {
  return items.filter((item) => item.skillId !== skillId);
}

export function addQueueTarget(
  items: QueueEntry[],
  skillId: string,
  target: TargetKey
): QueueEntry[] {
  const existing = items.find((item) => item.skillId === skillId);
  if (!existing) {
    return [...items, { skillId, targets: [target] }];
  }
  if (existing.targets.includes(target)) {
    return items;
  }
  return items.map((item) =>
    item.skillId === skillId ? { ...item, targets: [...item.targets, target] } : item
  );
}

export function removeQueueTarget(
  items: QueueEntry[],
  skillId: string,
  target: TargetKey
): QueueEntry[] {
  return items
    .map((item) =>
      item.skillId === skillId
        ? { ...item, targets: item.targets.filter((t) => t !== target) }
        : item
    )
    .filter((item) => item.targets.length > 0);
}

export function clearQueue(_items: QueueEntry[]): QueueEntry[] {
  return [];
}
