/**
 * EconomicDataResponse 数据新鲜度工具
 *
 * lastDataDate: 扫描响应里所有数值序列,返回「最后有数据点」的日期
 * (各序列各自最后一个非空点对应 dates 的最大者)。
 * 供更新按钮按数据实际新鲜度决定亮/灰,替代纯 localStorage 视角。
 */
import type { EconomicDataResponse } from '@/lib/types/economic';

export function lastDataDate(
  response: EconomicDataResponse | null | undefined,
): string | null {
  if (!response?.dates?.length) return null;
  const dates = response.dates;
  let last: string | null = null;

  const scanArray = (arr: unknown): void => {
    if (!Array.isArray(arr)) return;
    for (let i = arr.length - 1; i >= 0; i--) {
      const v = arr[i];
      if (v == null || (typeof v === 'number' && Number.isNaN(v))) continue;
      const d = dates[i];
      if (typeof d === 'string' && (last === null || d > last)) last = d;
      break; // 只看该序列的最后一个有效点
    }
  };

  const scanValue = (v: unknown): void => {
    if (Array.isArray(v)) {
      scanArray(v);
      return;
    }
    if (v && typeof v === 'object') {
      Object.values(v as Record<string, unknown>).forEach(scanValue);
    }
  };

  // 排除 dates 自身(日期轴非数值序列)
  Object.entries(response)
    .filter(([key]) => key !== 'dates')
    .forEach(([, value]) => scanValue(value));

  return last;
}
