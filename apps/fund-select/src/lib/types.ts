/**
 * 共享类型（与后端 src/api/models.py 对齐）
 */

/** 同类排名百分位：{pct: 当前排名÷同类总数×100, total: 同类总数}；缺失/异常 → null */
export interface RankPercentile {
  pct: number | null;
  total: number | null;
}

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
  /** 同类排名（雪球蛋卷基金）：4 个周期；债基 tab 永远 null */
  rank_ytd: RankPercentile | null;
  rank_1y:  RankPercentile | null;
  rank_3y:  RankPercentile | null;
  rank_5y:  RankPercentile | null;
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

/** 筛选维度（均可空 = 不限制）+ 排除 QDII 开关；min_sharpe 仅股票/市场股基 tab 使用 */
export interface FundFilters {
  min_age: number | null;
  min_size_yi: number | null;
  max_dd_3y: number | null;
  min_mgr_exp: number | null;
  min_sharpe: number | null;
  exclude_qdii: boolean;
  /** akshare 基金类型（粗分类），null = 走 tab 默认 universe */
  market_types: string[] | null;
  sort: string;
  order: 'asc' | 'desc';
}

export const DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 5,
  min_mgr_exp: 5,
  min_sharpe: null,
  exclude_qdii: false,
  market_types: null,
  sort: 'ret_3y',
  order: 'desc',
};

/** 股票基金 tab 默认筛选（决策：3 / 5 / 30 / 5 / 夏普 0.8，按 ret_3y desc） */
export const STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 30,
  min_mgr_exp: 5,
  min_sharpe: 0.8,
  exclude_qdii: false,
  market_types: null,
  sort: 'ret_3y',
  order: 'desc',
};

/** 债基·市场 tab 默认筛选：默认 universe = ['债券型','定开债券']，按 size_yi desc */
export const DISCOVERY_BOND_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 5,
  min_mgr_exp: 5,
  min_sharpe: null,
  exclude_qdii: false,
  market_types: ['债券型', '定开债券'],
  sort: 'size_yi',
  order: 'desc',
};

/** 股基·市场 tab 默认筛选：默认 universe = ['股票型','指数型','混合型','QDII']，按 ret_3y desc */
export const DISCOVERY_STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 30,
  min_mgr_exp: 5,
  min_sharpe: 0.8,
  exclude_qdii: false,
  market_types: ['股票型', '指数型', '混合型', 'QDII'],
  sort: 'ret_3y',
  order: 'desc',
};

/** akshare `基金类型` 字段的全部已知枚举（market tab 维度选项全集） */
export const MARKET_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '债券型', label: '债券型' },
  { value: '定开债券', label: '定开债券' },
  { value: '股票型', label: '股票型' },
  { value: '指数型', label: '指数型' },
  { value: '混合型', label: '混合型' },
  { value: 'QDII', label: 'QDII' },
  { value: '货币型', label: '货币型' },
  { value: 'FOF', label: 'FOF' },
];

/** 债基·市场 tab 可选基金类型（默认 universe 同 DEFAULT_DISCOVERY_UNIVERSE） */
export const BOND_MARKET_TYPE_OPTIONS = MARKET_TYPE_OPTIONS.filter(
  o => DEFAULT_DISCOVERY_UNIVERSE_CODES.bond.includes(o.value)
);

/** 股基·市场 tab 可选基金类型 */
export const STOCK_MARKET_TYPE_OPTIONS = MARKET_TYPE_OPTIONS.filter(
  o => DEFAULT_DISCOVERY_UNIVERSE_CODES.stock.includes(o.value)
);

/** 后端 DEFAULT_DISCOVERY_UNIVERSE 的前端镜像（UI 选项对齐后端默认 universe） */
const DEFAULT_DISCOVERY_UNIVERSE_CODES: Record<'bond' | 'stock', string[]> = {
  bond: ['债券型', '定开债券'],
  stock: ['股票型', '指数型', '混合型', 'QDII'],
};

/** 业绩排名一行（详情页用） */
export interface FundAchievementRank {
  period_kind: string;
  period: string;
  ret: number | null;
  peer_rank: string | null;
}
