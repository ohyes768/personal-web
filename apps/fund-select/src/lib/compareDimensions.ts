/**
 * 债基对比维度定义
 *
 * 高亮（最优标记）：规模、成立年限、经理从业、近3年回撤（min-abs）、
 *                  近1/3/5年收益、年费（min）
 * 只展示：利率债占比、申购费、赎回各档
 * 不含近1年回撤（主表无此列，PRD 约定）
 */
import type { CompareDimension } from '@/components/CompareTable';
import type { FundListItem } from './types';

const pct = (v: number) => `${v.toFixed(2)}%`;
const signedPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
const years = (v: number) => `${v.toFixed(1)}年`;
const yi = (v: number) => `${v.toFixed(2)}亿`;

/** 参与最优高亮的维度 */
export const fundCompareDimensions: Array<CompareDimension<FundListItem>> = [
  { key: 'size_yi', label: '规模', extract: f => f.size_yi, format: yi, direction: 'max' },
  { key: 'age_years', label: '成立年限', extract: f => f.age_years, format: years, direction: 'max' },
  { key: 'mgr_exp', label: '经理从业年限', extract: f => f.mgr_experience_years, format: years, direction: 'max' },
  { key: 'dd_3y', label: '近3年最大回撤', extract: f => f.dd_3y, format: pct, direction: 'min-abs' },
  { key: 'ret_1y', label: '近1年收益', extract: f => f.ret_1y, format: signedPct, direction: 'max' },
  { key: 'ret_3y', label: '近3年收益', extract: f => f.ret_3y, format: signedPct, direction: 'max' },
  { key: 'ret_5y', label: '近5年收益', extract: f => f.ret_5y, format: signedPct, direction: 'max' },
  { key: 'fee_annual', label: '年费', extract: f => f.fee_annual, format: pct, direction: 'min' },
];

/** 只展示、不参与高亮 */
export const fundDisplayOnlyDimensions: Array<CompareDimension<FundListItem>> = [
  { key: 'rate_bond_pct', label: '利率债占比', extract: f => f.rate_bond_pct, format: pct },
];

/**
 * 申购/赎回档需要详情接口数据（列表 DTO 不含）。
 * 抽屉打开时按需拉详情合并，见 useCompareDetail。
 */
export const feeDetailDimensions: Array<CompareDimension<FundListItem & {
  fees?: {
    fee_buy_small: number | null;
    fee_redeem_lt7d: number | null;
    fee_redeem_7d_1y: number | null;
    fee_redeem_ge1y: number | null;
    fee_redeem_ge7d: number | null;
  };
}>> = [
  { key: 'fee_buy_small', label: '申购费(小额档)', extract: f => f.fees?.fee_buy_small ?? null, format: pct },
  { key: 'fee_redeem_lt7d', label: '赎回 <7天', extract: f => f.fees?.fee_redeem_lt7d ?? null, format: pct },
  { key: 'fee_redeem_7d_1y', label: '赎回 7天~1年', extract: f => f.fees?.fee_redeem_7d_1y ?? null, format: pct },
  { key: 'fee_redeem_ge1y', label: '赎回 ≥1年', extract: f => f.fees?.fee_redeem_ge1y ?? null, format: pct },
  { key: 'fee_redeem_ge7d', label: '赎回 ≥7天', extract: f => f.fees?.fee_redeem_ge7d ?? null, format: pct },
];
