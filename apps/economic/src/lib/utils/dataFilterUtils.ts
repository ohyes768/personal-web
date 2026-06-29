/**
 * 数据过滤工具
 * 复制自 packages/shared-utils/src/dataFilterUtils.ts
 * 阶段二：apps/economic 拆离 monorepo
 */
import type { EconomicDataResponse, TabType } from '../types/economic';

/**
 * 过滤每月数据（每月首行）
 * 改用"月份变化"判别而非"日 === 1"：
 * - 后端 ffill 月度数据到 us_treasuries 交易日序列后，1 号若为周末会被推到 2 号或 3 号
 * - 旧逻辑 `getDate() === 1` 会把这类月份整月丢弃（典型：2025-02 周六 → 2025-02-03）
 * - 新逻辑：相邻两行月份不同就代表新一月开始，取该行
 */
export function filterMonthlyData(data: EconomicDataResponse): EconomicDataResponse {
  if (!data || !data.dates || data.dates.length === 0) {
    return data;
  }

  const monthlyIndices: number[] = [];
  let prevMonth = '';

  for (let i = 0; i < data.dates.length; i++) {
    const month = data.dates[i].slice(0, 7); // 'YYYY-MM'
    if (month !== prevMonth) {
      monthlyIndices.push(i);
      prevMonth = month;
    }
  }

  if (monthlyIndices.length === 0) {
    return {
      dates: [],
      us_treasuries: { '3m': [], '2y': [], '10y': [] },
      eu_treasuries: { '3m': [], '2y': [], '10y': [] },
      jp_treasuries: { '3m': [], '2y': [], '10y': [] },
      exchange_rates: {
        dollar_index: [],
        usd_cny: [],
        usd_jpy: [],
        usd_eur: [],
      },
    };
  }

  const filteredDates = monthlyIndices.map(i => data.dates[i]);

  const filterByIndices = (array: number[], indices: number[]) => indices.map(i => array[i]);

  return {
    dates: filteredDates,
    us_treasuries: {
      '3m': filterByIndices(data.us_treasuries['3m'] ?? [], monthlyIndices),
      '2y': filterByIndices(data.us_treasuries['2y'] ?? [], monthlyIndices),
      '10y': filterByIndices(data.us_treasuries['10y'] ?? [], monthlyIndices),
    },
    eu_treasuries: {
      '3m': filterByIndices(data.eu_treasuries['3m'] ?? [], monthlyIndices),
      '2y': filterByIndices(data.eu_treasuries['2y'] ?? [], monthlyIndices),
      '10y': filterByIndices(data.eu_treasuries['10y'] ?? [], monthlyIndices),
    },
    jp_treasuries: {
      '3m': filterByIndices(data.jp_treasuries['3m'] ?? [], monthlyIndices),
      '2y': filterByIndices(data.jp_treasuries['2y'] ?? [], monthlyIndices),
      '10y': filterByIndices(data.jp_treasuries['10y'] ?? [], monthlyIndices),
    },
    exchange_rates: {
      dollar_index: filterByIndices(data.exchange_rates?.dollar_index ?? [], monthlyIndices),
      usd_cny: filterByIndices(data.exchange_rates?.usd_cny ?? [], monthlyIndices),
      usd_jpy: filterByIndices(data.exchange_rates?.usd_jpy ?? [], monthlyIndices),
      usd_eur: filterByIndices(data.exchange_rates?.usd_eur ?? [], monthlyIndices),
    },
  };
}

/**
 * 根据Tab类型过滤数据
 */
export function filterDataByTab(
  data: EconomicDataResponse | null,
  tabType: TabType,
  timeRange: string
): EconomicDataResponse | null {
  if (!data) {
    return null;
  }

  if (tabType === 'fund-flow') {
    return null;
  }

  if (tabType === 'bonds') {
    const filteredData: EconomicDataResponse = {
      dates: data.dates,
      eu_treasuries: {
        '3m': data.eu_treasuries?.['3m'] ?? [],
        '2y': data.eu_treasuries?.['2y'] ?? [],
        '10y': data.eu_treasuries?.['10y'] ?? [],
      },
      jp_treasuries: {
        '3m': data.jp_treasuries?.['3m'] ?? [],
        '2y': data.jp_treasuries?.['2y'] ?? [],
        '10y': data.jp_treasuries?.['10y'] ?? [],
      },
      us_treasuries: { '3m': [], '2y': [], '10y': [] },
      exchange_rates: {
        dollar_index: [],
        usd_cny: [],
        usd_jpy: [],
        usd_eur: [],
      },
    };

    return filteredData;
  }

  return data;
}

/**
 * 检查日期是否是1号
 */
export function isFirstOfMonth(dateStr: string): boolean {
  const date = new Date(dateStr);
  return date.getDate() === 1;
}
