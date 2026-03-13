/**
 * 资金流向类型定义
 */

// 后端返回的累计数据响应
export interface CumulativeData {
  north_cumulative: CumulativeItem;
  south_cumulative: CumulativeItem;
}

export interface CumulativeItem {
  date: string;
  cum_7d?: number;
  cum_30d?: number;
}

// 后端返回的历史数据项
export interface HistoryDataItem {
  date: string;
  north_net?: number;    // 北向净流入
  north_buy?: number;    // 北向买入
  north_sell?: number;   // 北向卖出
  south_net?: number;    // 南向净流入
  south_buy?: number;    // 南向买入
  south_sell?: number;   // 南向卖出
}

// 后端返回的历史数据响应
export interface HistoryDataResponse {
  data: HistoryDataItem[];
}

// 前端图表数据格式（TradingView Lightweight Charts）
export interface ChartData {
  time: number;          // Unix timestamp (秒)
  northNet: number;      // 北向净流入
  southNet: number;      // 南向净流入
  netFlow: number;       // 净流入
}

// 时间范围类型
export type TimeRange = '1M' | '3M' | '6M' | '1Y' | 'ALL';

// 时间范围配置
export const TIME_RANGES: Record<TimeRange, string> = {
  '1M': '1个月',
  '3M': '3个月',
  '6M': '6个月',
  '1Y': '1年',
  'ALL': '全部',
} as const;