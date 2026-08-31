/**
 * 宏观信号分组的元数据 + 指标中文翻译表
 */
import type { DailyDimensionKey, DimensionKey } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';

/** 6 大分组元数据(color 仅卡头色点用,与评分无关) */
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

/** 月度模式只展示统计局/央行月频四维；外部压力、市场情绪只在日频 */
export const MONTHLY_GROUPS: DimensionKey[] = [
  'monetary_policy',
  'money_supply',
  'entity_economy',
  'inflation',
];

/** 全部分组 key（GROUP_META / 空快照类型用；月度渲染请用 MONTHLY_GROUPS） */
export const GROUP_ORDER: DimensionKey[] = [
  ...MONTHLY_GROUPS,
  'exchange_rate',
  'risk_appetite',
];

/** 日频模式卡片:3 维度 7 指标(key 对齐后端 _DAILY_INDICATORS,数组顺序即展示顺序) */
export const DAILY_GROUPS: Array<{ key: DailyDimensionKey; indicators: string[] }> = [
  { key: 'monetary_policy', indicators: ['dr007'] },
  { key: 'exchange_rate',   indicators: ['dollar_index', 'usd_cny', 'ted_spread', 'hibor_overnight'] },
  { key: 'risk_appetite',   indicators: ['volume', 'turnover', 'margin'] },
];

/**
 * indicator key → 中文 label + 单位 + 小数位
 * 查不到的 key fallback 到 { label: key, digits: 2 }
 */
export const INDICATOR_LABELS: Record<string, { label: string; unit?: string; digits?: number }> = {
  // 货币政策
  dr007:              { label: 'DR007',              unit: '%',  digits: 3 },
  lpr_1y:             { label: '1年期 LPR',          unit: '%',  digits: 2 },
  lpr_5y:             { label: '5年期 LPR',          unit: '%',  digits: 2 },
  mlf_1y:             { label: '1年期 MLF',          unit: '%',  digits: 2 },
  mlf_net_yi:         { label: 'MLF 净投放',         unit: '亿', digits: 0 },
  // 信用扩张
  m2_yoy:             { label: 'M2 同比',            unit: '%',  digits: 1 },
  m1_yoy:             { label: 'M1 同比',            unit: '%',  digits: 1 },
  social_yoy:         { label: '社融存量同比',        unit: '%', digits: 1 },
  m2_m1_spread:       { label: 'M2-M1 剪刀差',       unit: '%', digits: 1 },
  spread_change_pp:   { label: '剪刀差环比',         unit: 'pp', digits: 1 },
  // 经济运行
  pmi_manufacturing:  { label: '制造业 PMI',         unit: '%', digits: 1 },
  industrial_yoy:     { label: '工业增加值同比',     unit: '%', digits: 1 },
  fai_yoy:            { label: '固定资产投资同比',   unit: '%', digits: 1 },
  retail_yoy:         { label: '社零同比',           unit: '%', digits: 1 },
  electricity_yoy:    { label: '工业用电量同比',     unit: '%', digits: 1 },
  railway_yoy:        { label: '铁路货运量同比',     unit: '%', digits: 1 },
  keqiang_index:      { label: '克强指数',           unit: '%', digits: 1 },
  // 通胀环境
  cpi_yoy:            { label: 'CPI 同比',           unit: '%',  digits: 1 },
  ppi_yoy:            { label: 'PPI 同比',           unit: '%',  digits: 1 },
  core_cpi_yoy:       { label: '核心 CPI 同比',      unit: '%', digits: 1 },
  // 外部压力
  dollar_index:       { label: '美元指数',           digits: 2 },
  usd_cny:            { label: '美元兑人民币',                  digits: 4 },
  north_turnover_7d_yi:    { label: '北向7日日均成交额', unit: '亿', digits: 0 },
  north_turnover_today_yi: { label: '北向当日成交额',     unit: '亿', digits: 0 },
  north_change_pct:   { label: '北向7日环比',        unit: '%', digits: 1 },
  ted_spread:         { label: 'TED 利差',           unit: '%', digits: 2 },
  hibor_overnight:    { label: 'HIBOR 隔夜',         unit: '%', digits: 3 },
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
  // 日频快照 key(= market-sentiment 曲线序列名)
  volume:             { label: '两市成交额',         unit: '亿', digits: 0 },
  turnover:           { label: '换手率',             unit: '%',  digits: 2 },
  margin:             { label: '融资融券余额',       unit: '亿', digits: 0 },
  // 中文 key（后端/skill 直接以中文指标名作为 key 输出时的映射）
  '两市成交额':        { label: '两市成交额',         unit: '亿', digits: 0 },
  '换手率':            { label: '换手率',             unit: '%',  digits: 2 },
  '融资融券余额':      { label: '融资融券余额',       unit: '亿', digits: 0 },
};

/** 取 indicator label meta,查不到 fallback */
export function getIndicatorMeta(key: string): { label: string; unit?: string; digits?: number } {
  return INDICATOR_LABELS[key] ?? { label: key, digits: 2 };
}

/** 单个档位(对齐各 skill SKILL.md 评分框架的总分映射表) */
export interface ScaleLevel {
  /** 展示文本 */
  label: string;
  /** 总分区间 [min, max),用于 total_score 定位当前档 */
  min: number;
  max: number;
  /** conclusion 等价表述(skill 实际输出可能不等于 label,如「偏宽松」= 适度宽松) */
  aliases?: string[];
  /** 当前档位高亮色 */
  activeClass: string;
}

/** 6 大分组的档位刻度,数组顺序 = 总分从高到低 */
export const GROUP_SCALES: Record<DimensionKey, ScaleLevel[]> = {
  // 货币政策: ≥80 明显宽松 | 60-79 适度宽松 | 40-59 中性 | 20-39 适度紧缩 | <20 明显紧缩
  monetary_policy: [
    { label: '明显宽松', min: 80, max: 100, activeClass: 'text-emerald-400' },
    { label: '适度宽松', min: 60, max: 80, aliases: ['偏宽松', '宽松'], activeClass: 'text-emerald-300' },
    { label: '中性',     min: 40, max: 60, aliases: ['稳健'], activeClass: 'text-amber-300' },
    { label: '适度紧缩', min: 20, max: 40, aliases: ['偏紧缩', '偏紧', '边际收紧'], activeClass: 'text-rose-300' },
    { label: '明显紧缩', min: 0,  max: 20, aliases: ['紧缩'], activeClass: 'text-rose-400' },
  ],
  // 信用扩张: ≥80 明显信用扩张 | 60-79 适度信用扩张 | 40-59 中性 | 20-39 适度信用收缩 | <20 明显信用收缩
  money_supply: [
    { label: '明显扩张', min: 80, max: 100, aliases: ['明显信用扩张'], activeClass: 'text-emerald-400' },
    { label: '适度扩张', min: 60, max: 80, aliases: ['适度信用扩张', '信用扩张', '扩张'], activeClass: 'text-emerald-300' },
    { label: '中性',     min: 40, max: 60, activeClass: 'text-amber-300' },
    { label: '适度收缩', min: 20, max: 40, aliases: ['适度信用收缩', '信用收缩', '收缩'], activeClass: 'text-rose-300' },
    { label: '明显收缩', min: 0,  max: 20, aliases: ['明显信用收缩'], activeClass: 'text-rose-400' },
  ],
  // 经济运行: ≥80 经济过热 | 60-79 经济偏热 | 40-59 经济稳健 | 20-39 经济偏冷 | <20 经济过冷
  entity_economy: [
    { label: '过热', min: 80, max: 100, aliases: ['经济过热'], activeClass: 'text-rose-400' },
    { label: '偏热', min: 60, max: 80, aliases: ['经济偏热'], activeClass: 'text-orange-300' },
    { label: '稳健', min: 40, max: 60, aliases: ['经济稳健', '平稳'], activeClass: 'text-emerald-300' },
    { label: '偏冷', min: 20, max: 40, aliases: ['经济偏冷'], activeClass: 'text-sky-300' },
    { label: '过冷', min: 0,  max: 20, aliases: ['经济过冷'], activeClass: 'text-blue-400' },
  ],
  // 通胀环境: ≥80 明显通胀偏高 | 60-79 通胀温和偏高 | 40-59 温和/低位 | 20-39 低通胀 | <20 通缩风险
  inflation: [
    { label: '明显偏高', min: 80, max: 100, aliases: ['明显通胀偏高', '通胀偏高', '偏高'], activeClass: 'text-rose-400' },
    { label: '温和偏高', min: 60, max: 80, aliases: ['通胀温和偏高'], activeClass: 'text-orange-300' },
    { label: '温和',     min: 40, max: 60, aliases: ['通胀温和/低位', '温和/低位', '低位', '低通胀'], activeClass: 'text-emerald-300' },
    { label: '偏低',     min: 20, max: 40, aliases: ['通胀偏低'], activeClass: 'text-sky-300' },
    { label: '通缩风险', min: 0,  max: 20, aliases: ['通缩'], activeClass: 'text-blue-400' },
  ],
  // 外部压力: ≥80 极度风险规避 | 60-79 风险偏好偏低 | 40-59 中性 | 30-39 风险偏好偏高 | <30 极度乐观(区间特殊)
  exchange_rate: [
    { label: '极度风险规避', min: 80, max: 100, aliases: ['风险规避'], activeClass: 'text-rose-400' },
    { label: '风险偏低',     min: 60, max: 80, aliases: ['风险偏好偏低'], activeClass: 'text-orange-300' },
    { label: '中性',         min: 40, max: 60, aliases: ['外部中性'], activeClass: 'text-amber-300' },
    { label: '风险偏高',     min: 30, max: 40, aliases: ['风险偏好偏高'], activeClass: 'text-emerald-300' },
    { label: '极度乐观',     min: 0,  max: 30, activeClass: 'text-emerald-400' },
  ],
  // 市场情绪: ≥80 极度亢奋 | 60-79 偏热/乐观 | 40-59 中性 | 20-39 偏冷/谨慎 | <20 极度恐慌
  risk_appetite: [
    { label: '极度亢奋',  min: 80, max: 100, aliases: ['亢奋'], activeClass: 'text-rose-400' },
    { label: '偏热/乐观', min: 60, max: 80, aliases: ['偏热乐观', '偏热', '乐观'], activeClass: 'text-orange-300' },
    { label: '中性',      min: 40, max: 60, activeClass: 'text-amber-300' },
    { label: '偏冷/谨慎', min: 20, max: 40, aliases: ['偏冷谨慎', '偏冷', '谨慎'], activeClass: 'text-sky-300' },
    { label: '极度恐慌',  min: 0,  max: 20, aliases: ['恐慌'], activeClass: 'text-blue-400' },
  ],
};

/**
 * 定位当前档位:conclusion 文本匹配优先(保证与卡头主信号一致),
 * 匹配不上回退 total_score 区间;都失败返回 null(轴上不高亮)。
 * 文本匹配只做 conclusion.includes(alias) 单向包含,避免「温和」误配「温和偏高」。
 */
export function findActiveLevel(
  groupKey: DimensionKey,
  conclusion: string | null,
  totalScore?: number | null,
): ScaleLevel | null {
  const levels = GROUP_SCALES[groupKey];
  if (!levels) return null;
  if (conclusion) {
    const byText = levels.find(
      l => l.label === conclusion || (l.aliases ?? []).some(a => conclusion.includes(a)),
    );
    if (byText) return byText;
  }
  if (totalScore != null) {
    return levels.find(l => totalScore >= l.min && totalScore < l.max) ?? null;
  }
  return null;
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
  // 日频快照指标 → 对应曲线 Tab
  dr007:        'rates',
  hibor_overnight: 'liquidity-risk',
  volume:       'market-sentiment',
  turnover:     'market-sentiment',
  margin:       'market-sentiment',
  '美元指数':     'treasury-exchange',
  '美元兑人民币': 'treasury-exchange',
  'TED利差':      'rates',
};
