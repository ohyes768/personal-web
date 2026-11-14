import type { DividendStock } from './types';
import type { FavoritesResponse } from './watchlist';

export interface ScreeningConditions {
  min_yield: number;
  min_roe: number;
  min_roe_avg_3y: number;
  max_quarter_profit_decline_pct: number;
  /** 扣非净利润3年复合增长率下限（%）；0 = 三年不缩水（默认），可为负 */
  min_cagr_3y: number;
  exchange?: string;
}
export const DEFAULT_SCREENING: ScreeningConditions = { min_yield: 3.5, min_roe: 10, min_roe_avg_3y: 10, max_quarter_profit_decline_pct: 30, min_cagr_3y: 0 };
/** 选股关注页保存筛选条件的 localStorage 键（阅读页复用同一份条件） */
export const SCREENING_STORAGE_KEY = 'dividend-screening-conditions-v1';
/** Decode browser storage while preserving legacy conditions without the new threshold. */
export function restoreScreeningConditions(stored: unknown): ScreeningConditions {
  if (!stored || typeof stored !== 'object') return { ...DEFAULT_SCREENING };
  const values = stored as Record<string, unknown>;
  const keys = ['min_yield', 'min_roe', 'min_roe_avg_3y'] as const;
  if (!keys.every(key => typeof values[key] === 'number' && Number.isFinite(values[key]) && values[key] >= 0 && values[key] <= 100)) return { ...DEFAULT_SCREENING };
  const decline = Object.prototype.hasOwnProperty.call(values, 'max_quarter_profit_decline_pct') ? values.max_quarter_profit_decline_pct : DEFAULT_SCREENING.max_quarter_profit_decline_pct;
  if (typeof decline !== 'number' || !Number.isFinite(decline) || decline <= 0 || decline > 100) return { ...DEFAULT_SCREENING };
  // 老存储没有 CAGR 条件时用默认值，不清空用户已设的其它条件
  const cagr = Object.prototype.hasOwnProperty.call(values, 'min_cagr_3y') ? values.min_cagr_3y : DEFAULT_SCREENING.min_cagr_3y;
  if (typeof cagr !== 'number' || !Number.isFinite(cagr) || cagr < -100 || cagr > 100) return { ...DEFAULT_SCREENING };
  return {
    min_yield: values.min_yield as number,
    min_roe: values.min_roe as number,
    min_roe_avg_3y: values.min_roe_avg_3y as number,
    max_quarter_profit_decline_pct: decline,
    min_cagr_3y: cagr,
    exchange: values.exchange === '沪市主板' || values.exchange === '深市主板' ? values.exchange : undefined,
  };
}

export type ScreeningStatus = 'eligible' | 'excluded' | 'insufficient_data';
export interface ScreeningItem {
  stock: DividendStock;
  status: ScreeningStatus;
  reasons: string[];
  warnings: string[];
}
export interface ScreeningResponse {
  items: ScreeningItem[];
  counts: Record<ScreeningStatus, number>;
  conditions: ScreeningConditions;
  last_updated: string | null;
  financial_last_updated?: string | null;
  dividend_years: number[];
  total: number;
}

/** 单条筛选条件的判定结果 */
export type ScreeningCheckResult = 'pass' | 'fail' | 'missing' | 'warn';
/** 后端逐条判定（判定规则与选股关注页同源，见 backend screening_service.build_checks） */
export interface ScreeningCheck {
  key: string;
  label: string;
  result: ScreeningCheckResult;
  value_text: string;
  threshold_text: string;
  detail: string;
  reason: string;
  warning: string;
}
/** 单股筛选复核响应 */
export interface StockScreeningResponse {
  code: string;
  name: string;
  status: ScreeningStatus;
  reasons: string[];
  warnings: string[];
  checks: ScreeningCheck[];
  conditions: ScreeningConditions;
  last_updated: string | null;
  financial_last_updated: string | null;
}

/** 判定结果的中文标签 */
export const SCREENING_CHECK_LABELS: Record<ScreeningCheckResult, string> = {
  pass: '符合',
  fail: '不符',
  missing: '待补',
  warn: '提示',
};

/** 逐条判定的计数（阅读页摘要用） */
export interface ScreeningCheckSummary {
  pass: number;
  fail: number;
  missing: number;
  warn: number;
  total: number;
}

export function summarizeChecks(checks: ScreeningCheck[] | null | undefined): ScreeningCheckSummary {
  const summary: ScreeningCheckSummary = { pass: 0, fail: 0, missing: 0, warn: 0, total: 0 };
  for (const check of checks ?? []) {
    summary.total += 1;
    if (check.result === 'pass') summary.pass += 1;
    else if (check.result === 'fail') summary.fail += 1;
    else if (check.result === 'missing') summary.missing += 1;
    else if (check.result === 'warn') summary.warn += 1;
  }
  return summary;
}

/** 读取选股关注页保存的条件；没有保存或损坏时用默认条件 */
export function readStoredScreeningConditions(): ScreeningConditions {
  if (typeof window === 'undefined') return { ...DEFAULT_SCREENING };
  try {
    return restoreScreeningConditions(JSON.parse(window.localStorage.getItem(SCREENING_STORAGE_KEY) || 'null'));
  } catch {
    return { ...DEFAULT_SCREENING };
  }
}

/** 批量筛选状态的最小条目（阅读页下拉列表标注用） */
export interface ScreeningStatusItem {
  code: string;
  status: ScreeningStatus;
}
/** 批量筛选状态响应 */
export interface ScreeningStatusesResponse {
  items: ScreeningStatusItem[];
  total: number;
  conditions: ScreeningConditions;
}

/** 状态到下拉列表前缀标记的映射（✓ 符合 / ✗ 不符 / ？待补） */
export function screeningStatusMark(status: ScreeningStatus): string {
  if (status === 'eligible') return '✓';
  if (status === 'excluded') return '✗';
  return '?';
}

/** 条件是否就是默认条件（用于阅读页说明「当前筛选条件」来源） */
export function isDefaultScreeningConditions(conditions: ScreeningConditions): boolean {
  return (['min_yield', 'min_roe', 'min_roe_avg_3y', 'max_quarter_profit_decline_pct', 'min_cagr_3y'] as const)
    .every(key => conditions[key] === DEFAULT_SCREENING[key]);
}
export interface BatchFavoriteResponse {
  items: { code: string; status: 'added' | 'already_exists' | 'failed'; error?: string }[];
  favorites: FavoritesResponse;
}
