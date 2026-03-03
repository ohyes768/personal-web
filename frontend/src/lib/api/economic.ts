/**
 * 经济数据 API 封装
 */
import { apiClient } from './client';
import type { EconomicDataResponse } from '../types/economic';

export const economicApi = {
  /**
   * 获取宏观经济数据
   */
  getData: async (startDate?: string, endDate?: string): Promise<EconomicDataResponse> => {
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    return apiClient.get<EconomicDataResponse>('/api/macro/data', params);
  },

  /**
   * 更新数据（通过 Gateway）
   */
  updateData: async () => {
    return apiClient.post('/api/macro/update');
  },
};
