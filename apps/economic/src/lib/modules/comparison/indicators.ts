/**
 * 20 个指标的注册表（按数据源分组）
 * 颜色与现有 chartConfig.ts 的 CHART_COLORS 保持一致
 */
import type { IndicatorId, IndicatorMeta } from './types';

export const INDICATORS: Record<IndicatorId, IndicatorMeta> = {
  // 美债
  us_3m:  { id: 'us_3m',  label: '美债3m',   group: 'us_treasury', color: '#3b82f6', unit: '%',     source: 'FRED' },
  us_2y:  { id: 'us_2y',  label: '美债2y',   group: 'us_treasury', color: '#60a5fa', unit: '%',     source: 'FRED' },
  us_10y: { id: 'us_10y', label: '美债10y',  group: 'us_treasury', color: '#93c5fd', unit: '%',     source: 'FRED' },

  // 德债
  eu_3m:  { id: 'eu_3m',  label: '德债3m',   group: 'eu_treasury', color: '#f59e0b', unit: '%',     source: 'FRED' },
  eu_2y:  { id: 'eu_2y',  label: '德债2y',   group: 'eu_treasury', color: '#fbbf24', unit: '%',     source: 'ECB'  },
  eu_10y: { id: 'eu_10y', label: '德债10y',  group: 'eu_treasury', color: '#fcd34d', unit: '%',     source: 'FRED' },

  // 日债
  jp_10y: { id: 'jp_10y', label: '日债10y',  group: 'jp_treasury', color: '#ef4444', unit: '%',     source: 'FRED' },

  // 中债
  cn_10y: { id: 'cn_10y', label: '中债10y',  group: 'cn_treasury', color: '#f87171', unit: '%',     source: 'AKShare' },

  // 汇率
  dxy:     { id: 'dxy',     label: '美元指数', group: 'exchange',   color: '#10b981', unit: '',      source: 'FRED' },
  usd_cny: { id: 'usd_cny', label: 'USD/CNY', group: 'exchange',   color: '#34d399', unit: '',      source: 'FRED' },
  usd_jpy: { id: 'usd_jpy', label: 'USD/JPY', group: 'exchange',   color: '#6ee7b7', unit: '',      source: 'FRED' },
  usd_eur: { id: 'usd_eur', label: 'USD/EUR', group: 'exchange',   color: '#a7f3d0', unit: '',      source: 'FRED' },

  // 恐慌
  vix:     { id: 'vix',     label: 'VIX恐慌',  group: 'volatility',  color: '#a855f7', unit: '',      source: 'FRED' },

  // 资金流
  north_net: { id: 'north_net', label: '北向净流入', group: 'fund_flow', color: '#06b6d4', unit: '亿元', source: 'AKShare' },
  south_net: { id: 'south_net', label: '南向净流入', group: 'fund_flow', color: '#22d3ee', unit: '亿元', source: 'AKShare' },

  // 利率利差
  ted_spread: { id: 'ted_spread', label: 'TED利差', group: 'rates',  color: '#ec4899', unit: '%',    source: 'FRED' },
  sofr:       { id: 'sofr',       label: 'SOFR',   group: 'rates',  color: '#f472b6', unit: '%',    source: 'FRED' },

  // 商品
  gold:   { id: 'gold',   label: '黄金', group: 'commodity', color: '#eab308', unit: '元/克', source: '阿里云' },
  silver: { id: 'silver', label: '白银', group: 'commodity', color: '#94a3b8', unit: '元/克', source: '阿里云' },
  oil:    { id: 'oil',    label: '原油', group: 'commodity', color: '#1e293b', unit: '$/桶',  source: '阿里云' },
  copper: { id: 'copper', label: '铜',   group: 'commodity', color: '#b45309', unit: '$/吨',  source: '阿里云' },
};

/** 数据源分组的显示顺序（与经济页 tab 顺序一致） */
export const GROUP_ORDER: Array<{ group: string; label: string }> = [
  { group: 'us_treasury', label: '美债' },
  { group: 'eu_treasury', label: '德债' },
  { group: 'jp_treasury', label: '日债' },
  { group: 'cn_treasury', label: '中债' },
  { group: 'exchange',    label: '汇率' },
  { group: 'volatility',  label: '恐慌' },
  { group: 'fund_flow',   label: '资金流' },
  { group: 'rates',       label: '利率利差' },
  { group: 'commodity',   label: '商品' },
];

/** 指标默认选择（DXY + 美债10y + VIX，对比模块入口案例） */
export const DEFAULT_INDICATORS: IndicatorId[] = ['dxy', 'us_10y', 'vix', 'gold'];

/** 最多可选指标数 */
export const MAX_INDICATORS = 6;
