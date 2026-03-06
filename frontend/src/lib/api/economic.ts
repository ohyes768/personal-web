/**
 * 经济数据 API 封装
 */
import { apiClient } from './client';
import type { EconomicDataResponse } from '../types/economic';

export const economicApi = {
  getData: async (startDate?: string, endDate?: string): Promise<EconomicDataResponse> => {
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    // apiClient.get 已经返回 result.data，不需要再访问 .data
    return apiClient.get<EconomicDataResponse>('/macro/data', params);
  },

  /**
   * 更新数据（通过 API Gateway）
   */
  updateData: async () => {
    return apiClient.post('/macro/update');
  },
};
