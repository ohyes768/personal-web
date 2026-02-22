/**
 * 经济数据 API 封装
 */
import { apiClient } from './client';
import type { ExchangeRateData } from './types';

export const economicApi = {
  /**
   * 获取汇率数据
   */
  getExchangeRates: (timeRange: string = '1Y') =>
    apiClient.get<ExchangeRateData[]>('/api/economic/exchange-rates', {
      time_range: timeRange
    }),

  /**
   * 获取美债收益率数据
   */
  getTreasuryYields: (timeRange: string = '1Y') =>
    apiClient.get('/api/economic/treasury-yields', {
      time_range: timeRange
    }),

  /**
   * 获取债务GDP数据
   */
  getDebtGdp: (timeRange: string = '1Y') =>
    apiClient.get('/api/economic/debt-gdp', {
      time_range: timeRange
    }),

  /**
   * 获取TGA/HIBOR数据
   */
  getTgaHibor: (timeRange: string = '1Y') =>
    apiClient.get('/api/economic/tga-hibor', {
      time_range: timeRange
    }),
};
