/**
 * 共享类型（与后端 src/api/models.py 对齐）
 */

/** 同类排名百分位：{pct: 当前排名÷同类总数×100, total: 同类总数, rank: 同类排名分子}；缺失/异常 → null */
export interface RankPercentile {
  pct: number | null;
  total: number | null;
  rank: number | null;
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
  /** 分页（仅前端 state，写入 URL）；page=1 / limit=50 默认值不进 URL */
  page: number;
  limit: number;
}

/** 每页条数选项（与后端 limit 取值范围 1-200 对齐） */
export const LIMIT_OPTIONS = [25, 50, 100] as const;

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
  page: 1,
  limit: 50,
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
  page: 1,
  limit: 50,
};

/** 债基·市场 tab 默认筛选：默认 universe = 5 个粗类别全选 */
export const DISCOVERY_BOND_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 5,
  min_mgr_exp: 5,
  min_sharpe: null,
  exclude_qdii: false,
  market_types: ['纯债型', '混合型', '指数型', 'QDII', 'REITs'],
  sort: 'size_yi',
  order: 'desc',
  page: 1,
  limit: 50,
};

/** 股基·市场 tab 默认筛选：默认 universe = 5 个粗类别全选 */
export const DISCOVERY_STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 30,
  min_mgr_exp: 5,
  min_sharpe: 0.8,
  exclude_qdii: false,
  market_types: ['股票型', '混合型', '指数型', 'QDII', 'REITs'],
  sort: 'ret_3y',
  order: 'desc',
  page: 1,
  limit: 50,
};

/** 基金类型（market tab 维度选项全集） */
export const MARKET_TYPE_OPTIONS: { value: string; label: string }[] = [
  // 股基·市场 5 个粗类别
  { value: '股票型', label: '股票型' },
  { value: '混合型', label: '混合型' },
  { value: '指数型', label: '指数型' },
  { value: 'QDII', label: 'QDII' },
  { value: 'REITs', label: 'REITs' },
];

/** 债基·市场 5 个粗类别（"纯债型" 是股基的"股票型" 在债基的对应物） */
export const BOND_MARKET_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '纯债型', label: '纯债型' },
  { value: '混合型', label: '混合债基' },
  { value: '指数型', label: '指数债' },
  { value: 'QDII', label: 'QDII 债' },
  { value: 'REITs', label: 'REITs' },
];

/** 股基·市场 5 个粗类别（与 BOND_MARKET_TYPE_OPTIONS 同结构，value 不同） */
export const STOCK_MARKET_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '股票型', label: '股票型' },
  { value: '混合型', label: '混合型' },
  { value: '指数型', label: '指数型' },
  { value: 'QDII', label: 'QDII' },
  { value: 'REITs', label: 'REITs' },
];

/**
 * 粗类别 → 后端精确 market_subtype 映射
 * 前端 UI 选粗类别，发送时映射成精确 subtype 列表传给后端 IN 过滤
 */
export const COARSE_TO_SUBTYPES_STOCK: Record<string, string[]> = {
  '股票型': ['股票型'],
  '混合型': ['混合型-平衡', '混合型-绝对收益', '混合型-灵活'],
  '指数型': ['指数型-海外股票', '指数型-其他'],
  'QDII': ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活', 'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs'],
  'REITs': ['Reits', 'REITs'],
};

export const COARSE_TO_SUBTYPES_BOND: Record<string, string[]> = {
  '纯债型': ['债券型-中短债', '债券型-混合一级', '债券型-混合二级', '债券型-利率债', '债券型-信用债', '债券型-长期纯债'],
  '混合型': ['债券型-混合债'],  // 混合债基（区别于混合一级/二级）
  '指数型': ['指数型-固收'],
  'QDII': ['QDII-纯债', 'QDII-混合债'],
  'REITs': [],  // 债基 universe 不含 REITs
};

/** 把 UI 粗类别展开成精确 subtype 列表（去重保序） */
export function coarseToSubtypes(
  coarse: string[],
  mapping: Record<string, string[]>,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of coarse) {
    for (const s of mapping[c] ?? []) {
      if (!seen.has(s)) {
        seen.add(s);
        out.push(s);
      }
    }
  }
  return out;
}

/**
 * 全量刷新预筛参数（discovery-* tab）
 * 后端 /full/refresh 端点参数；max_nav_stale_days 后端固定 14，不暴露
 */
export interface FullRefreshFilters {
  /** 近 3 年涨 ≥ X%（L1 字段，预筛 2） */
  min_ret_3y: number | null;
  /** 规模 ≥ Y 亿（L2 字段，预筛 3） */
  min_size_yi: number | null;
  /** 经理从业 ≥ W 年（L0 字段，预筛 1） */
  min_mgr_exp: number | null;
}

export const DEFAULT_FULL_REFRESH_FILTERS: FullRefreshFilters = {
  min_ret_3y: 20,
  min_size_yi: 5,
  min_mgr_exp: 5,
};

/** 业绩排名一行（详情页用） */
export interface FundAchievementRank {
  period_kind: string;
  period: string;
  ret: number | null;
  peer_rank: string | null;
}
