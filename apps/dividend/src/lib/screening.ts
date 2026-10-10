import type { DividendStock } from './types';
import type { FavoritesResponse } from './watchlist';

export interface ScreeningConditions {
  min_yield: number;
  min_roe: number;
  min_roe_avg_3y: number;
  max_quarter_profit_decline_pct: number;
  exchange?: string;
}
export const DEFAULT_SCREENING: ScreeningConditions = { min_yield: 3.5, min_roe: 10, min_roe_avg_3y: 10, max_quarter_profit_decline_pct: 30 };
/** Decode browser storage while preserving legacy conditions without the new threshold. */
export function restoreScreeningConditions(stored: unknown): ScreeningConditions {
  if (!stored || typeof stored !== 'object') return { ...DEFAULT_SCREENING };
  const values = stored as Record<string, unknown>;
  const keys = ['min_yield', 'min_roe', 'min_roe_avg_3y'] as const;
  if (!keys.every(key => typeof values[key] === 'number' && Number.isFinite(values[key]) && values[key] >= 0 && values[key] <= 100)) return { ...DEFAULT_SCREENING };
  const decline = Object.prototype.hasOwnProperty.call(values, 'max_quarter_profit_decline_pct') ? values.max_quarter_profit_decline_pct : DEFAULT_SCREENING.max_quarter_profit_decline_pct;
  if (typeof decline !== 'number' || !Number.isFinite(decline) || decline <= 0 || decline > 100) return { ...DEFAULT_SCREENING };
  return {
    min_yield: values.min_yield as number,
    min_roe: values.min_roe as number,
    min_roe_avg_3y: values.min_roe_avg_3y as number,
    max_quarter_profit_decline_pct: decline,
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
export interface BatchFavoriteResponse {
  items: { code: string; status: 'added' | 'already_exists' | 'failed'; error?: string }[];
  favorites: FavoritesResponse;
}
