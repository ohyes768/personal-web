/**
 * 经理维度类型与 API（/api/funds/managers/*，任务 11-10-fund-manager-evaluation）
 */
import { getJson } from './api';

export interface ManagerListItem {
  manager_id: string;
  name: string;
  company: string | null;
  career_years: number | null;
  current_scale_yi: number | null;
  current_fund_count: number | null;
  managed_fund_count: number | null;
  /** 管理时长加权年化 %（排除债基/货币/FOF 段） */
  weighted_annual: number | null;
  longest_tenure_annual: number | null;
  longest_tenure_years: number | null;
  /** 代表基金最大回撤 %（负值；按任职窗口切片计算） */
  max_drawdown: number | null;
  sharpe: number | null;
  calmar: number | null;
  representative_fund: string | null;
  /** 任期胜率 %（tenure_return>0 的任期占比；无回报数据时 null） */
  tenure_win_rate: number | null;
  /** 独管比例 %（在管基金中仅自己一位经理的占比） */
  solo_ratio: number | null;
  /** 代表作背离 pp（最长任期年化 − 加权年化；>15 视为代表作依赖） */
  rep_divergence: number | null;
}

export interface ManagerTenure {
  fund_code: string;
  fund_name: string | null;
  fund_type: string | null;
  size_yi: number | null;
  start_date: string | null;
  end_date: string | null;
  tenure_days: number | null;
  tenure_return: number | null;
  annual_return: number | null;
  is_current: boolean;
}

export interface ManagerDetail extends ManagerListItem {
  career_days: number | null;
  tenures: ManagerTenure[];
}

export interface ManagerScreenResponse {
  total: number;
  items: ManagerListItem[];
}

export interface ManagerFilters {
  min_career_years: number | null;
  min_weighted_annual: number | null;
  max_drawdown: number | null;
  min_scale_yi: number | null;
  min_win_rate: number | null;
  min_solo_ratio: number | null;
  /** 在管基金数 ≤ N（精力分散门槛；中基协硬性上限 10 只） */
  max_fund_count: number | null;
  keyword: string | null;
  sort: string;
  order: 'asc' | 'desc';
  page: number;
  limit: number;
}

export const MANAGER_DEFAULT_FILTERS: ManagerFilters = {
  // 分层默认值（11-12 调研：硬门槛 + 质量门槛；收益/回撤不默认卡，先看全貌）
  min_career_years: 5,        // 硬门槛：穿越一轮完整牛熊的及格线
  min_weighted_annual: null,
  max_drawdown: null,
  min_scale_yi: 5,            // 硬门槛：<2 亿有清盘风险，5 亿可投资范围已自由
  min_win_rate: 60,           // 质量门槛：胜率中位数 ~55%，60 即优于平均
  min_solo_ratio: 50,         // 质量门槛：过半在管为独管，共管贡献难归因
  max_fund_count: 8,          // 硬门槛：精力分散（中基协硬性上限 10，8 留缓冲）
  keyword: null,
  sort: 'weighted_annual',
  order: 'desc',
  page: 1,
  limit: 50,
};

const BASE = '/funds/api/funds/managers';

function buildQuery(f: Partial<ManagerFilters>): string {
  const params = new URLSearchParams();
  if (f.min_career_years != null) params.set('min_career_years', String(f.min_career_years));
  if (f.min_weighted_annual != null) params.set('min_weighted_annual', String(f.min_weighted_annual));
  if (f.max_drawdown != null) params.set('max_drawdown', String(f.max_drawdown));
  if (f.min_scale_yi != null) params.set('min_scale_yi', String(f.min_scale_yi));
  if (f.min_win_rate != null) params.set('min_win_rate', String(f.min_win_rate));
  if (f.min_solo_ratio != null) params.set('min_solo_ratio', String(f.min_solo_ratio));
  if (f.max_fund_count != null) params.set('max_fund_count', String(f.max_fund_count));
  if (f.keyword) params.set('keyword', f.keyword);
  if (f.sort) params.set('sort', f.sort);
  if (f.order) params.set('order', f.order);
  if (f.page != null && f.page > 1) params.set('page', String(f.page));
  if (f.limit != null && f.limit !== 50) params.set('limit', String(f.limit));
  const q = params.toString();
  return q ? `?${q}` : '';
}

export const managerApi = {
  screen(filters: Partial<ManagerFilters>, signal?: AbortSignal): Promise<ManagerScreenResponse> {
    return getJson(`${BASE}/screen${buildQuery(filters)}`, signal);
  },

  getDetail(managerId: string, signal?: AbortSignal): Promise<ManagerDetail> {
    return getJson(`${BASE}/${managerId}`, signal);
  },
};
