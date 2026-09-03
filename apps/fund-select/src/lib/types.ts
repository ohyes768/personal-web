/**
 * 共享类型（与后端 src/api/models.py 对齐）
 */

export interface FundListItem {
  code: string;
  name: string;
  fund_type: string;
  size_yi: number | null;
  age_years: number | null;
  dd_3y: number | null;
  ret_1m: number | null;
  ret_1y: number | null;
  ret_3y: number | null;
  ret_5y: number | null;
  sharpe: number | null;
  ir: number | null;
  alpha: number | null;
  gamma: number | null;
  alpha_ir: number | null;
  excess_3y: number | null;
  mgr_name: string | null;
  mgr_company: string | null;
  mgr_experience_years: number | null;
  rate_bond_pct: number | null;
  fee_mgmt: number | null;
  fee_custody: number | null;
  fee_service: number | null;
  fee_annual: number | null;
  updated_at: string | null;
}

export interface ScreenResponse {
  total: number;
  items: FundListItem[];
}

export interface FundFees {
  fee_buy_small: number | null;
  fee_redeem_lt7d: number | null;
  fee_redeem_7d_1y: number | null;
  fee_redeem_ge1y: number | null;
  fee_redeem_ge7d: number | null;
  fee_mgmt: number | null;
  fee_custody: number | null;
  fee_service: number | null;
}

export interface FundHoldings {
  report_date: string | null;
  rate_bond_pct: number | null;
  credit_bond_pct: number | null;
  convertible_pct: number | null;
  top5_concentration: number | null;
  top5_bonds: string | null;
}

export interface FundDetail extends FundListItem {
  established_date: string | null;
  mgr_days: number | null;
  is_active: boolean;
  ret_6m: number | null;
  dd_1y: number | null;
  dd_5y: number | null;
  nav_latest: number | null;
  nav_date: string | null;
  fees: FundFees;
  holdings: FundHoldings | null;
  achievement_ranks: FundAchievementRank[];
}

export interface StatsResponse {
  total: number;
  with_performance: number;
  with_fees: number;
  with_holdings: number;
  last_refresh_at: string | null;
}

export interface RefreshStatus {
  task_id: string;
  status: 'running' | 'done' | 'error';
  total: number;
  completed: number;
  failed: number;
  errors: string[];
}

/** 筛选四维度（均可空 = 不限制）+ 排除 QDII 开关 */
export interface FundFilters {
  min_age: number | null;
  min_size_yi: number | null;
  max_dd_3y: number | null;
  min_mgr_exp: number | null;
  exclude_qdii: boolean;
  sort: string;
  order: 'asc' | 'desc';
}

export const DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 5,
  min_mgr_exp: 5,
  exclude_qdii: false,
  sort: 'ret_3y',
  order: 'desc',
};

/** 股票基金 tab 默认筛选（决策：3 / 5 / 20 / 5，与债基一致按 ret_3y desc） */
export const STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 20,
  min_mgr_exp: 5,
  exclude_qdii: false,
  sort: 'ret_3y',
  order: 'desc',
};

/** 业绩排名一行（详情页用） */
export interface FundAchievementRank {
  period_kind: string;
  period: string;
  ret: number | null;
  peer_rank: string | null;
}
