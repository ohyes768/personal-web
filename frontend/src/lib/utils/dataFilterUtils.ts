/**
 * 数据过滤工具
 */
import type { EconomicDataResponse, TabType } from '../types/economic';

/**
 * 过滤每月1号的数据
 * @param data 原始经济数据
 * @returns 过滤后的月度数据
 */
export function filterMonthlyData(data: EconomicDataResponse): EconomicDataResponse {
  if (!data || !data.dates || data.dates.length === 0) {
    return data;
  }

  // 找到所有每月1号的索引
  const monthlyIndices: number[] = [];

  for (let i = 0; i < data.dates.length; i++) {
    const dateStr = data.dates[i];
    const date = new Date(dateStr);

    // 检查是否是1号
    if (date.getDate() === 1) {
      monthlyIndices.push(i);
    }
  }

  if (monthlyIndices.length === 0) {
    // 如果没有找到1号的数据，返回空数据
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

  // 根据索引提取数据
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
 * @param data 原始数据
 * @param tabType Tab类型
 * @param timeRange 时间范围
 * @returns 过滤后的数据
 */
export function filterDataByTab(
  data: EconomicDataResponse | null,
  tabType: TabType,
  timeRange: string
): EconomicDataResponse | null {
  if (!data) {
    return null;
  }

  // fund-flow Tab 不处理经济数据，返回空
  if (tabType === 'fund-flow') {
    return null;
  }

  // 如果是bonds Tab，只保留德债和日债数据
  if (tabType === 'bonds') {
    // 移除不需要的数据字段，保留德债和日债的所有期限数据
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

  // treasury-exchange Tab，返回所有数据
  return data;
}

/**
 * 检查日期是否是1号
 * @param dateStr 日期字符串 (YYYY-MM-DD)
 * @returns 是否是1号
 */
export function isFirstOfMonth(dateStr: string): boolean {
  const date = new Date(dateStr);
  return date.getDate() === 1;
}