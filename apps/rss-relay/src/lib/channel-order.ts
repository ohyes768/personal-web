import type { Channel } from './types';

/** 「未分类」是兜底系统渠道，列表展示时始终排最后，其余渠道保持原顺序。 */
export function unclassifiedLast(channels: Channel[]): Channel[] {
  return [...channels].sort((a, b) => Number(a.id === 'unclassified') - Number(b.id === 'unclassified'));
}
