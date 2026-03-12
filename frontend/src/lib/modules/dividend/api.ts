/**
 * 股息率模块 API 封装
 * 所有股息率相关 API 调用必须通过此文件
 */
import { directClient } from '@/lib/api/client';
import type {
  DividendListResponse,
  DividendQueryParams,
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
};