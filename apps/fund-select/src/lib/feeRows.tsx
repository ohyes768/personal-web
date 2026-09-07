/**
 * 费率明细行（fund-select 复用）
 *
 * 数据源：FundDetail.fees（后端 FundFees ORM 字段映射）
 * RowDetailDrawer（股票）+ RowDetailDrawerBond（债基）共用
 */
import type { FundDetail } from './types';

export interface FeeRow {
  key: keyof NonNullable<FundDetail['fees']>;
  label: string;
  suffix?: string;
}

export const FEE_ROWS: FeeRow[] = [
  { key: 'fee_buy_small',   label: '申购费(小额档)' },
  { key: 'fee_redeem_lt7d',  label: '赎回 <7天' },
  { key: 'fee_redeem_7d_1y', label: '赎回 7天~1年' },
  { key: 'fee_redeem_ge1y',  label: '赎回 ≥1年' },
  { key: 'fee_redeem_ge7d',  label: '赎回 ≥7天' },
  { key: 'fee_mgmt',         label: '管理费',     suffix: '/年' },
  { key: 'fee_custody',      label: '托管费',     suffix: '/年' },
  { key: 'fee_service',      label: '销售服务费', suffix: '/年' },
];
