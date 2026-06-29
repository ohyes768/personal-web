/**
 * 宏观经济数据类型定义
 * 复制自 packages/shared-types/src/economic.ts
 * 阶段二：apps/economic 拆离 monorepo
 */

/** 时间范围选项 */
export type TimeRange = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL';

/** Tab类型选项 */
export type TabType = 'treasury-exchange' | 'bonds' | 'fund-flow' | 'comparison' | 'commodities';

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
    '3m': number[];
    '2y': number[];
    '10y': number[];
  };
  jp_treasuries: {
    '3m': number[];
    '2y': number[];
    '10y': number[];
  };
  exchange_rates?: {
    dollar_index: number[];
    usd_cny: number[];
    usd_jpy: number[];
    usd_eur: number[];
  };
  vix?: number[];
  fund_flow?: {
    north_net_flow: (number | null)[];
    north_buy: (number | null)[];
    north_sell: (number | null)[];
    south_net_flow: (number | null)[];
    south_buy: (number | null)[];
    south_sell: (number | null)[];
  };
  china_bond?: {
    '10y': (number | null)[];
  };
  ted_spread?: {
    sofr: (number | null)[];
    us_3m: (number | null)[];
    ted_spread: (number | null)[];
  };
  commodities?: {
    gold: (number | null)[];
    silver: (number | null)[];
    oil: (number | null)[];
    copper: (number | null)[];
  };
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
  euroBond10Y: string;
  japanBond10Y: string;
  dollarIndex: string;
  usdCny: string;
  usdJpy: string;
  usdEur: string;
  vix: string;
}
