/**
 * 数据过滤工具
 * 复制自 packages/shared-utils/src/dataFilterUtils.ts
 * 阶段二：apps/macro 拆离 monorepo
 */
import type { EconomicDataResponse, TabType } from '../types/economic';

/**
 * 根据Tab类型过滤数据
 */
export function filterDataByTab(
  data: EconomicDataResponse | null,
  tabType: TabType,
  _timeRange: string
): EconomicDataResponse | null {
  if (!data) {
    return null;
  }

  if (tabType === 'fund-flow') {
    return null;
  }

  return data;
}
