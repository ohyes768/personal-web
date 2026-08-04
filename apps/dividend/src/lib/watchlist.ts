/**
 * 收藏股票（watchlist）API 封装
 */
import { directClient } from './api-client';
import type {
  AlertConfigRequest,
  AlertStatusResponse,
  AlertCheckResult,
} from './types';

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
  items: Array<FavoriteItem & { alerts?: import('./types').AlertConfig | null }>;
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

// ========== 挡位监控（alerts）==========

/**
 * 设置/更新单只股票的挡位监控（覆盖式，须先收藏）
 */
export const setAlerts = (code: string, body: AlertConfigRequest): Promise<FavoritesResponse> =>
  directClient.put<FavoritesResponse>(`/api/dividend/favorites/${code}/alerts`, body);

/**
 * 清除单只股票的挡位配置
 */
export const clearAlerts = (code: string): Promise<FavoritesResponse> =>
  directClient.delete<FavoritesResponse>(`/api/dividend/favorites/${code}/alerts`);

/**
 * 获取所有挡位状态 + 今日触发记录
 */
export const getAlertsStatus = (): Promise<AlertStatusResponse> =>
  directClient.get<AlertStatusResponse>('/api/dividend/favorites/alerts/status');

/**
 * 手动触发挡位检查（前端"测试推送"按钮用）
 */
export const checkAlerts = (): Promise<AlertCheckResult> =>
  directClient.post<AlertCheckResult>('/api/dividend/favorites/alerts/check', {});
