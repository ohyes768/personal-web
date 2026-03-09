/**
 * 宏观经济数据类型定义
 */

/** 时间范围选项 */
export type TimeRange = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL';

/** Tab类型选项 */
export type TabType = 'treasury-exchange' | 'bonds';

/** 时间范围配置 */
export interface TimeRangeConfig {
  label: string;
  value: TimeRange;
  days: number | null; // null表示全部
}

/** 美债收益率数据点 */
export interface USYieldDataPoint {
  date: string;
  rate_3m: number;
  rate_2y: number;
  rate_10y: number;
}

/** 汇率数据点 */
export interface ExchangeRateDataPoint {
  date: string;
  dollar_index: number;
  usd_cny: number;
  usd_jpy: number;
  usd_eur: number;
}

/** API响应数据 */
export interface EconomicDataResponse {
  dates: string[];
  us_treasuries: {
    '3m': number[];
    '2y': number[];
    '10y': number[];
  };
  eu_treasuries: {
    '3m': number[];    // 欧洲 3 个月期国债收益率
    '2y': number[];    // 欧洲 2 年期国债收益率
    '10y': number[];   // 欧洲 10 年期国债收益率
  };
  jp_treasuries: {
    '3m': number[];    // 日本 3 个月期国债收益率
    '2y': number[];    // 日本 2 年期国债收益率
    '10y': number[];   // 日本 10 年期国债收益率
  };
  exchange_rates?: {
    dollar_index: number[];
    usd_cny: number[];
    usd_jpy: number[];
    usd_eur: number[];
  };
  vix?: number[];  // VIX恐慌指数数据
}

/** 图表数据系列 */
export interface ChartTrace {
  x: string[];
  y: number[];
  name: string;
  mode: 'lines' | 'lines+markers';
  line?: {
    color: string;
    width: number;
  };
  xaxis?: string;
  yaxis?: string;
}

/** 缓存数据结构 */
export interface CacheEntry {
  timeRange: TimeRange;
  data: EconomicDataResponse;
  timestamp: number;
}

/** 图表颜色配置 */
export interface ChartColors {
  treasury3M: string;
  treasury2Y: string;
  treasury10Y: string;
  euroBond10Y: string;    // 欧债颜色
  japanBond10Y: string;   // 日债颜色
  dollarIndex: string;
  usdCny: string;
  usdJpy: string;
  usdEur: string;
  vix: string;  // VIX恐慌指数颜色（紫色）
}
