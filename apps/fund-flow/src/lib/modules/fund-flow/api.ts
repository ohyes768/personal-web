/**
 * 资金流向 API 客户端
 * 阶段二：apps/fund-flow 拆离 monorepo
 * 走前端 catch-all 代理（apps/fund-flow/src/app/api/fund-flow/[...path]/route.ts）
 */
import type { CumulativeData, HistoryDataResponse, ChartData } from './types';

/**
 * 获取累计数据（7日/30日）
 */
export async function getCumulativeData(): Promise<CumulativeData> {
  const response = await fetch('/api/fund-flow/cumulative');
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

/**
 * 获取历史数据（完整）
 */
export async function getHistoryData(): Promise<ChartData[]> {
  try {
    const response = await fetch('/api/fund-flow/history', {
      method: 'GET',
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result: HistoryDataResponse = await response.json();

    return result.data.map((item) => ({
      time: new Date(item.date).getTime() / 1000,
      northNet: item.north_net ?? 0,
      southNet: item.south_net ?? 0,
      netFlow: (item.north_net ?? 0) - (item.south_net ?? 0),
    }));
  } catch (error) {
    console.error('Failed to fetch history data:', error);
    throw error;
  }
}

/**
 * 手动更新数据
 */
export async function updateData(): Promise<{ message: string }> {
  try {
    const response = await fetch('/api/update/fund-flow', {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to update data:', error);
    throw error;
  }
}
