/**
 * 宏观信号分组的元数据 + 指标中文翻译表
 */
import type { DimensionKey } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';

/** 6 大分组元数据(calendarColor 仅日历色点用,与评分无关) */
export const GROUP_META: Record<DimensionKey, {
  title: string;
  order: number;
  calendarColor: string;
}> = {
  monetary_policy: { title: '货币政策', order: 1, calendarColor: 'bg-blue-500'    },
  money_supply:    { title: '信用扩张', order: 2, calendarColor: 'bg-emerald-500' },
  entity_economy:  { title: '经济运行', order: 3, calendarColor: 'bg-purple-500'  },
  inflation:       { title: '通胀环境', order: 4, calendarColor: 'bg-orange-500'  },
  exchange_rate:   { title: '外部压力', order: 5, calendarColor: 'bg-cyan-500'    },
  risk_appetite:   { title: '市场情绪', order: 6, calendarColor: 'bg-pink-500'    },
};

/** 分组按固定顺序排列的 key 列表 */
export const GROUP_ORDER: DimensionKey[] = [
  'monetary_policy',
  'money_supply',
  'entity_economy',
  'inflation',
  'exchange_rate',
  'risk_appetite',
];

/**
 * indicator key → 中文 label + 单位 + 小数位
 * 查不到的 key fallback 到 { label: key, digits: 2 }
 */
export const INDICATOR_LABELS: Record<string, { label: string; unit?: string; digits?: number }> = {
  // 货币政策
  dr007:              { label: 'DR007',              unit: '%',  digits: 3 },
  lpr_1y:             { label: '1年期 LPR',          unit: '%',  digits: 2 },
  mlf_1y:             { label: '1年期 MLF',          unit: '%',  digits: 2 },
  // 信用扩张
  m2_yoy:             { label: 'M2 同比',            unit: '%',  digits: 1 },
  m1_yoy:             { label: 'M1 同比',            unit: '%',  digits: 1 },
  social_yoy:         { label: '社融存量同比',        unit: '%', digits: 1 },
  // 经济运行
  pmi_manufacturing:  { label: '制造业 PMI',         unit: '%', digits: 1 },
  industrial_yoy:     { label: '工业增加值同比',     unit: '%', digits: 1 },
  fai_yoy:            { label: '固定资产投资同比',   unit: '%', digits: 1 },
  retail_yoy:         { label: '社零同比',           unit: '%', digits: 1 },
  electricity_yoy:    { label: '工业用电量同比',     unit: '%', digits: 1 },
  railway_yoy:        { label: '铁路货运量同比',     unit: '%', digits: 1 },
  // 通胀环境
  cpi_yoy:            { label: 'CPI 同比',           unit: '%',  digits: 1 },
  ppi_yoy:            { label: 'PPI 同比',           unit: '%',  digits: 1 },
  core_cpi_yoy:       { label: '核心 CPI 同比',      unit: '%', digits: 1 },
  // 外部压力
  dollar_index:       { label: '美元指数',           digits: 2 },
  usd_cny:            { label: '美元兑人民币',       digits: 4 },
  ted_spread:         { label: 'TED 利差',           unit: '%', digits: 2 },
  '美元指数':          { label: '美元指数',           digits: 2 },
  '美元兑人民币':      { label: '美元兑人民币',       digits: 4 },
  'TED利差':           { label: 'TED 利差',           unit: '%', digits: 2 },
  '北向7日日均成交额':  { label: '北向7日日均成交额',  unit: '亿', digits: 0 },
  '北向当日成交额':     { label: '北向当日成交额',     unit: '亿', digits: 0 },
  '北向7日环比':       { label: '北向7日环比',        unit: '%', digits: 2 },
  // 市场情绪
  total_amount_yi:    { label: '两市成交额',         unit: '亿', digits: 0 },
  turnover_rate:      { label: '换手率',             unit: '%',  digits: 2 },
  margin_balance_yi:  { label: '融资融券余额',       unit: '亿', digits: 0 },
  // 中文 key（后端/skill 直接以中文指标名作为 key 输出时的映射）
  '两市成交额':        { label: '两市成交额',         unit: '亿', digits: 0 },
  '换手率':            { label: '换手率',             unit: '%',  digits: 2 },
  '融资融券余额':      { label: '融资融券余额',       unit: '亿', digits: 0 },
};

/** 取 indicator label meta,查不到 fallback */
export function getIndicatorMeta(key: string): { label: string; unit?: string; digits?: number } {
  return INDICATOR_LABELS[key] ?? { label: key, digits: 2 };
}

/**
 * indicator key → 可跳转到的曲线图 Tab id
 * 只有现有 Tab 已有对应曲线的指标才列入,其他指标不显示「查看曲线」按钮
 */
export const INDICATOR_LINK_MAP: Record<string, TabType> = {
  // 外部压力 → 中美利差/汇率 / 利率利差
  dollar_index: 'treasury-exchange',
  usd_cny:      'treasury-exchange',
  ted_spread:   'rates',
  '美元指数':     'treasury-exchange',
  '美元兑人民币': 'treasury-exchange',
  'TED利差':      'rates',
};
