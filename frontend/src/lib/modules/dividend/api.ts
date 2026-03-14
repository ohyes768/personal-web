/**
 * 股息率模块 API 封装
 * 所有股息率相关 API 调用必须通过此文件
 */
import { directClient } from '@/lib/api/client';
import type {
  DividendListResponse,
  DividendQueryParams,
  StockPEResponse,
  M120ListResponse,
  RealtimePriceRequest,
  RealtimePriceResponse,
  StockInfoRequest,
  StockInfoResponse,
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
   * 获取 PE/PB 数据
   */
  getPEData: (params?: { code?: string; codes?: string }) =>
    directClient.get<StockPEResponse>('/api/dividend/pe', params),

  /**
   * 获取 M120 数据
   */
  getM120Data: (params?: { min_yield?: number; sort_by?: string; sort_order?: string }) =>
    directClient.get<M120ListResponse>('/api/dividend/m120', params),

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
};