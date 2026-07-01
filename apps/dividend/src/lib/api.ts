/**
 * 股息率模块 API 封装
 * 所有股息率相关 API 调用必须通过此文件
 */
import { directClient } from './api-client';
import type { FavoritesResponse } from './watchlist';
import type {
  DividendListResponse,
  DividendDetailResponse,
  DividendQueryParams,
  DividendStatusResponse,
  M120ListResponse,
  RealtimePriceRequest,
  RealtimePriceResponse,
  RefreshDividendResponse,
  StockInfoRequest,
  StockInfoResponse,
  BoardInfoResponse,
  BoardInfoRequest,
  AuxDataStatus,
} from './types';

export const dividendApi = {
  /**
   * 获取股票列表
   */
  getStocks: (params?: DividendQueryParams) =>
    directClient.get<DividendListResponse>('/api/dividend/stocks', params),

  /**
   * 获取股票详情
   */
  getStockDetail: (code: string) =>
    directClient.get<DividendDetailResponse>(`/api/dividend/stocks/${code}`),

  /**
   * 获取 M120 数据
   */
  getM120Data: (params?: { min_yield?: number; sort_by?: string; sort_order?: string }) =>
    directClient.get<M120ListResponse>('/api/dividend/m120', params),

  /**
   * 获取 M120 数据状态
   */
  getM120Status: (params?: { min_yield?: number }) =>
    directClient.get<{ needs_update: boolean; last_updated: string | null; file_exists: boolean; missing_count: number; missing_codes: string[] }>('/api/dividend/m120/status', params),

  /**
   * 获取股息率数据状态
   */
  getDividendStatus: () =>
    directClient.get<DividendStatusResponse>('/api/dividend/dividend/status'),

  /**
   * 获取申万行业数据状态
   */
  getSwIndustryStatus: () =>
    directClient.get<AuxDataStatus>('/api/dividend/sw-industry/status'),

  /**
   * 获取股东户数数据状态
   */
  getShareholderStatus: () =>
    directClient.get<AuxDataStatus>('/api/dividend/shareholder/status'),

  /**
   * 获取个股板块映射数据状态
   */
  getBoardStatus: () =>
    directClient.get<AuxDataStatus>('/api/dividend/board/status'),

  /**
   * 获取实时收盘价和偏离度
   */
  getRealtimePrice: (data: RealtimePriceRequest) =>
    directClient.post<RealtimePriceResponse>('/api/dividend/realtime-price', data),

  /**
   * 批量获取股票行业/概念信息
   */
  getStocksInfo: (data: StockInfoRequest) =>
    directClient.post<StockInfoResponse>('/api/dividend/stocks/info', data),

  /**
   * 获取股票板块信息（概念板块/行业板块）
   */
  getBoardInfo: (params: BoardInfoRequest) =>
    directClient.get<BoardInfoResponse>('/api/dividend/board', params),

  /**
   * 获取股票 PE/PB 数据
   */
  getPEData: (params: { codes?: string; code?: string }) =>
    directClient.get<{ items: Array<{ code: string; pe: number | null; pb: number | null }>; total: number }>('/api/dividend/pe', params),

  /**
   * 获取财务指标数据状态
   */
  getFinancialStatus: () =>
    directClient.get<AuxDataStatus>('/api/dividend/financial/status'),

  /**
   * 获取收藏列表
   */
  getFavorites: () =>
    directClient.get<FavoritesResponse>('/api/dividend/favorites'),

  /**
   * 添加一只股票到收藏
   */
  addFavorite: (code: string) =>
    directClient.post<FavoritesResponse>(`/api/dividend/favorites/${code}`),

  /**
   * 从收藏中移除
   */
  removeFavorite: (code: string) =>
    directClient.delete<FavoritesResponse>(`/api/dividend/favorites/${code}`),
};

/**
 * 数据更新 API
 */
export const dividendUpdateApi = {
  /**
   * 更新股息率核心数据
   * 从红利指数获取股票列表，调用 akshare 计算股息率
   */
  refreshDividend: () =>
    directClient.post<RefreshDividendResponse>('/api/dividend/dividend/refresh', { min_dividend: 10 }),

  /**
   * 更新 M120 数据（每周一次）
   * 获取指定股票的 120 日均线数据
   */
  refreshM120: (codes?: string[]) =>
    directClient.post<{ success: boolean; message: string; count?: number }>(
      '/api/dividend/m120/refresh',
      codes ? { codes } : undefined
    ),

  /**
   * 更新实时价格（每日一次）
   * 使用 comrms 批量接口获取指定股票的实时价格
   */
  refreshRealtimePrice: (codes?: string[]) =>
    directClient.post<{ success: boolean; message: string; count?: number }>(
      '/api/dividend/realtime/refresh',
      codes ? { codes } : undefined
    ),

  /**
   * 更新财务指标数据
   */
  refreshFinancial: (codes?: string[], force = false) =>
    directClient.post<{ success: boolean; message: string; count?: number; missing_count?: number }>(
      `/api/dividend/financial/refresh${force ? '?force=true' : ''}`,
      codes ? { codes } : undefined
    ),

  /**
   * 更新申万行业数据
   */
  refreshSwIndustry: (force = false) =>
    directClient.post<{ success: boolean; message: string; count: number; quarter: string }>(
      `/api/dividend/sw-industry/refresh${force ? '?force=true' : ''}`, {}
    ),

  /**
   * 更新股东户数数据
   */
  refreshShareholder: (force = false) =>
    directClient.post<{ success: boolean; message: string; count: number; quarter: string }>(
      `/api/dividend/shareholder/refresh${force ? '?force=true' : ''}`, {}
    ),

  /**
   * 更新个股板块映射数据
   * @param codes 可选股票代码列表；不传=全量刷新，传=增量补缺
   * @param force 是否强制刷新（忽略 90 天节流，仅全量模式生效）
   */
  refreshBoardMapping: (codes?: string[], force = false) =>
    directClient.post<{ success: boolean; message: string; mode?: string }>(
      `/api/dividend/board/refresh${force ? '?force=true' : ''}`,
      codes ? { codes } : undefined
    ),
};
