/**
 * Economic 模块 API 封装
 * 所有 Economic 相关 API 调用必须通过此文件
 */
import { apiClient, directClient } from '@/lib/api-client';
import type { EconomicDataResponse, TabType } from '@/lib/types/economic';
import type { IndicatorId } from '@/lib/modules/comparison/types';
import type { MacroSignalSnapshot } from '@/lib/modules/macro-signal/types';

export interface UpdateResponse {
  success: boolean;
  message: string;
  updated_at?: string;
  error_code?: string;
}

/** 多端点写入必须串行：routes 全局 _is_updating，并发会 UPDATE_IN_PROGRESS。 */
async function postSerial(paths: readonly string[]): Promise<UpdateResponse> {
  let last: UpdateResponse | undefined;
  for (const path of paths) {
    const res = await directClient.post<UpdateResponse>(path);
    if (!res.success) return res;
    last = res;
  }
  if (!last) {
    return { success: false, message: 'empty serial post list' };
  }
  return last;
}

export const economicApi = {
  /**
   * 月度宏观信号快照。模块级引用稳定，避免父组件重渲染导致 MacroSignalTab 重复请求。
   * 无数据时后端 404，调用方 catch；成功但 data 缺失时返回 null。
   */
  getSignalSnapshot: async (month: string): Promise<MacroSignalSnapshot | null> => {
    const data = await apiClient.get<MacroSignalSnapshot | null>('/api/macro/signal', { month });
    return data ?? null;
  },

  /**
   * 按 Tab 获取全历史经济数据（切换 Tab 时调用，时间周期由前端本地切片）
   * 对比页请用 getComparisonData，不要打无 indicators 的 /data/comparison
   */
  getTabData: (
    tab: Exclude<TabType, 'macro-signal' | 'comparison'>,
    startDate: string = '2000-01-01'
  ): Promise<EconomicDataResponse> => {
    return apiClient.get<EconomicDataResponse>(`/api/macro/data/${tab}`, {
      start_date: startDate,
    });
  },

  /**
   * 对比页按需拉指标：GET /api/macro/data/comparison?indicators=a,b&start_date=2000-01-01
   */
  getComparisonData: (
    ids: IndicatorId[],
    startDate: string = '2000-01-01'
  ): Promise<EconomicDataResponse> => {
    return apiClient.get<EconomicDataResponse>('/api/macro/data/comparison', {
      indicators: ids.join(','),
      start_date: startDate,
    });
  },

  /**
   * 综合更新（n8n 调用入口，不在前端用）
   */
  updateData: () => {
    return apiClient.post<UpdateResponse>('/api/macro/update');
  },

  /**
   * 初始化历史数据（首次部署用）
   * 串行：美债 → 汇率 → 中债 history
   */
  initHistory: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/fetch/us-treasuries/history',
      '/api/macro/fetch/exchange-rates/history',
      '/api/macro/fetch/china-bonds/history',
    ]);
  },

  /**
   * 初始化商品历史数据（首次部署用）
   * 调 /api/macro/fetch/commodities/history
   */
  initCommoditiesHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/commodities/history');
  },

  /**
   * 更新美债 + 汇率 + 中国 10y（前端中美利差/汇率 tab 用）
   */
  updateUsTreasuriesAndRates: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/update/us-treasuries',
      '/api/macro/update/exchange-rates',
      '/api/macro/update/china-bonds',
    ]);
  },

  /**
   * 更新商品数据（黄金/白银/原油/铜，统一走阿里云 alirmcom2）
   */
  updateCommodities: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/commodities');
  },

  /**
   * 初始化股指历史数据（首次部署用）
   * 5 个全球指数（恒生/上证/标普500/纳指/道指）5 年全量 K 线
   * 调 /api/macro/fetch/indices/history
   */
  initIndicesHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/indices/history');
  },

  /**
   * 增量更新股指数据（统一走阿里云 alirmcom2 comkm K线接口）
   * 调 /api/macro/update/indices
   */
  updateIndices: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/indices');
  },

  /**
   * 初始化 VIX 历史数据（首次部署用）
   * 调 /api/macro/fetch/vix/history
   */
  initVIXHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/vix/history');
  },

  /**
   * 增量更新 VIX 数据（最近 7 天）
   * 调 /api/macro/update/vix
   */
  updateVIX: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/vix');
  },

  /**
   * 初始化 TGA 历史数据（首次部署用，FRED WTREGEN）
   * 调 /api/macro/fetch/tga/history
   */
  initTGAHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/tga/history');
  },

  /**
   * 增量更新 TGA 数据（最近 7 天）
   * 调 /api/macro/update/tga
   */
  updateTGA: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/tga');
  },

  /**
   * 初始化 HIBOR 历史数据（首次部署用，HKMA API）
   * 调 /api/macro/fetch/hibor/history
   */
  initHIBORHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/hibor/history');
  },

  /**
   * 增量更新 HIBOR 数据（最近 7 天）
   * 调 /api/macro/update/hibor
   */
  updateHIBOR: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/hibor');
  },

  /**
   * 初始化流动性/风险历史数据（首次部署用）
   * 串行：vix → tga → hibor history
   */
  initLiquidityHistory: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/fetch/vix/history',
      '/api/macro/fetch/tga/history',
      '/api/macro/fetch/hibor/history',
    ]);
  },

  /**
   * 增量更新流动性/风险数据
   * 串行：vix → tga → hibor update
   */
  updateLiquidity: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/update/vix',
      '/api/macro/update/tga',
      '/api/macro/update/hibor',
    ]);
  },

  /**
   * 初始化利率利差历史数据（首次部署用）
   * 串行：中债 → TED → DR007 → 美债 history
   */
  initRatesHistory: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/fetch/china-bonds/history',
      '/api/macro/fetch/ted-spread/history',
      '/api/macro/fetch/dr007/history',
      '/api/macro/fetch/us-treasuries/history',
    ]);
  },

  /**
   * 增量更新利率利差数据
   * 串行：中债 → TED → DR007 → 美债 update
   */
  updateRates: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/update/china-bonds',
      '/api/macro/update/ted-spread',
      '/api/macro/update/dr007',
      '/api/macro/update/us-treasuries',
    ]);
  },

  /**
   * 当日更新两市成交额（BaoStock 近 10 日窗口）
   */
  updateVolume: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/volume');
  },

  /**
   * 当日更新两市换手率（BaoStock 近 10 日窗口）
   */
  updateTurnover: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/turnover');
  },

  /**
   * 当日更新融资余额（akshare 当日点）
   */
  updateMargin: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/update/margin');
  },

  /**
   * 初始化市场情绪历史：串行 volume-turnover → margin → fund-flow。
   * 三条 /fetch/.../history 端点共用 routes 全局 _is_updating 锁。
   */
  initMarketSentimentHistory: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/fetch/volume-turnover/history',
      '/api/macro/fetch/margin/history',
      '/api/macro/fetch/fund-flow/history',
    ]);
  },

  /**
   * 增量更新市场情绪：串行 volume → turnover → margin → fund-flow
   */
  updateMarketSentiment: (): Promise<UpdateResponse> => {
    return postSerial([
      '/api/macro/update/volume',
      '/api/macro/update/turnover',
      '/api/macro/update/margin',
      '/api/macro/update/fund-flow',
    ]);
  },
};
