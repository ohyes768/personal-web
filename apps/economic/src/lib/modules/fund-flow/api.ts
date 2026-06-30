/**
 * 资金流向 API 客户端
 */
import { directClient } from '@/lib/api-client';
import type { UpdateResponse } from '@/lib/modules/economic/api';
import type { CumulativeData, HistoryDataResponse, ChartData } from './types';

/**
 * 获取累计数据（7日/30日）
 */
export async function getCumulativeData(): Promise<CumulativeData> {
  return directClient.get<CumulativeData>('/api/macro/fund-flow/cumulative');
}

/**
 * 获取历史数据（完整）
 */
export async function getHistoryData(): Promise<ChartData[]> {
  const result = await directClient.get<HistoryDataResponse>('/api/macro/fund-flow/history');

  // 转换为图表数据格式
  return result.data.map((item) => ({
    time: new Date(item.date).getTime() / 1000, // 转换为 Unix timestamp（秒）
    northNet: item.north_net ?? 0,
    southNet: item.south_net ?? 0,
    netFlow: (item.north_net ?? 0) - (item.south_net ?? 0),
  }));
}

/**
 * 初始化资金流向历史数据（首次部署用）
 * 调 /api/macro/fetch/fund-flow/history，从 2014-11-17 拉全量
 */
export async function initHistory(): Promise<UpdateResponse> {
  return directClient.post<UpdateResponse>('/api/macro/fetch/fund-flow/history');
}

/**
 * 增量更新资金流向数据（日级）
 */
export async function updateData(): Promise<UpdateResponse> {
  return directClient.post<UpdateResponse>('/api/macro/update/fund-flow');
}
