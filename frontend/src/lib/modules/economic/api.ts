/**
 * Economic 模块 API 封装
 * 所有 Economic 相关 API 调用必须通过此文件
 */
import { apiClient } from '@/lib/api/client';
import type { EconomicDataResponse } from './types';

export const economicApi = {
  /**
   * 获取经济数据
   */
  getData: (startDate?: string, endDate?: string): Promise<EconomicDataResponse> => {
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    return apiClient.get<EconomicDataResponse>('/api/macro/data', params);
  },

  /**
   * 更新数据
   */
  updateData: () => {
    return apiClient.post('/api/macro/update');
  },
};