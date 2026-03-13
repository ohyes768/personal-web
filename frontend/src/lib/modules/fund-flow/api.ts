/**
 * 资金流向 API 客户端
 */
import { directClient } from '@/lib/api/client';
import type { CumulativeData, HistoryDataResponse, ChartData } from './types';

// 全局宏观数据服务端口
const MACRO_API_BASE = 'http://localhost:8094';

/**
 * 获取累计数据（7日/30日）
 */
export async function getCumulativeData(): Promise<CumulativeData> {
  const response = await fetch(`${MACRO_API_BASE}/api/fund-flow/cumulative`);
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
    const response = await fetch(`${MACRO_API_BASE}/api/fund-flow/history`, {
      method: 'GET',
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result: HistoryDataResponse = await response.json();

    // 转换为图表数据格式
    return result.data.map((item) => ({
      time: new Date(item.date).getTime() / 1000, // 转换为 Unix timestamp（秒）
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
    const response = await fetch(`${MACRO_API_BASE}/api/macro/update/fund-flow`, {
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