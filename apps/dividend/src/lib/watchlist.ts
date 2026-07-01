/**
 * 收藏股票（watchlist）API 封装
 */
import { directClient } from './api-client';

export interface FavoriteItem {
  code: string;
  added_at: string;
  note: string | null;
}

export interface FavoritesNotify {
  enabled: boolean;
  rules: unknown[];
  last_notified_at: string | null;
}

export interface FavoritesResponse {
  version: number;
  updated_at: string;
  total: number;
  codes: string[];
  items: FavoriteItem[];
  notify: FavoritesNotify;
}

/**
 * 获取完整收藏列表
 */
export const getFavorites = (): Promise<FavoritesResponse> =>
  directClient.get<FavoritesResponse>('/api/dividend/favorites');

/**
 * 添加一只股票到收藏（幂等）
 */
export const addFavorite = (code: string): Promise<FavoritesResponse> =>
  directClient.post<FavoritesResponse>(`/api/dividend/favorites/${code}`);

/**
 * 从收藏中移除（幂等）
 */
export const removeFavorite = (code: string): Promise<FavoritesResponse> =>
  directClient.delete<FavoritesResponse>(`/api/dividend/favorites/${code}`);
