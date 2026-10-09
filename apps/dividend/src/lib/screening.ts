import type { DividendStock } from './types';
import type { FavoritesResponse } from './watchlist';

export interface ScreeningConditions {
  min_yield: number;
  min_roe: number;
  min_roe_avg_3y: number;
  exchange?: string;
}
export const DEFAULT_SCREENING: ScreeningConditions = { min_yield: 3.5, min_roe: 10, min_roe_avg_3y: 10 };
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
