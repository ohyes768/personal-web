/**
 * 股息率模块 API 封装
 * 所有股息率相关 API 调用必须通过此文件
 */
import { directClient } from '@personal-web/api-client';
import type {
  DividendListResponse,
  DividendQueryParams,
  M120ListResponse,
  RealtimePriceRequest,
  RealtimePriceResponse,
  StockInfoRequest,
  StockInfoResponse,
  BoardInfoResponse,
  BoardInfoRequest,
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
    directClient.get(`/api/dividend/stocks/${code}`),

  /**
   * 获取 M120 数据
   */
  getM120Data: (params?: { min_yield?: number; sort_by?: string; sort_order?: string }) =>
    directClient.get<M120ListResponse>('/api/dividend/m120', params),

  /**
   * 获取 M120 数据状态
   */
  getM120Status: () =>
    directClient.get<{ needs_update: boolean; last_updated: string | null; file_exists: boolean }>('/api/dividend/m120/status'),

  /**
   * 获取股息率数据状态
   */
  getDividendStatus: () =>
    directClient.get<{ needs_update: boolean; last_updated: string | null; file_exists: boolean }>('/api/dividend/dividend/status'),

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
   * 获取 PE/PB 数据
   */
  getPEData: (params: { codes?: string; code?: string }) =>
    directClient.get<{ items: Array<{ code: string; pe: number | null; pb: number | null }>; total: number }>('/api/dividend/pe', params),
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
    directClient.post<{ success: boolean; message: string }>('/api/dividend/dividend/refresh', { min_dividend: 10 }),

  /**
   * 更新 M120 数据（每周一次）
   * 获取所有股息率 > 3% 股票的 120 日均线数据
   */
  refreshM120: () =>
    directClient.post<{ success: boolean; message: string; count?: number }>('/api/dividend/m120/refresh'),

  /**
   * 更新实时价格（每日一次）
   * 使用 comrms 批量接口获取所有股票的实时价格
   */
  refreshRealtimePrice: () =>
    directClient.post<{ success: boolean; message: string; count?: number }>('/api/dividend/realtime/refresh'),
};
