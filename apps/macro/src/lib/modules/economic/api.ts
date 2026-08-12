/**
 * Economic 模块 API 封装
 * 所有 Economic 相关 API 调用必须通过此文件
 */
import { apiClient, directClient } from '@/lib/api-client';
import type { EconomicDataResponse } from '@/lib/types/economic';

export interface UpdateResponse {
  success: boolean;
  message: string;
  updated_at?: string;
  error_code?: string;
}

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
   * 综合更新（n8n 调用入口，不在前端用）
   */
  updateData: () => {
    return apiClient.post<UpdateResponse>('/api/macro/update');
  },

  /**
   * 初始化历史数据（首次部署用）
   * 并发调两个 /fetch/.../history 端点，从 2000-01-01 拉全量数据
   * 任一成功即视为成功（与 updateUsTreasuriesAndRates 同模式）
   */
  initHistory: async (): Promise<UpdateResponse> => {
    const [us, fx] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/fetch/us-treasuries/history'),
      directClient.post<UpdateResponse>('/api/macro/fetch/exchange-rates/history'),
    ]);
    return us.success || fx.success ? us : us;
  },

  /**
   * 初始化德债 + 日债历史数据（首次部署用）
   * 并发调两个 history 端点，任一成功即视为成功
   */
  initBondsHistory: async (): Promise<UpdateResponse> => {
    const [eu, jp] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/fetch/eu-bonds/history'),
      directClient.post<UpdateResponse>('/api/macro/fetch/jp-bonds/history'),
    ]);
    return eu.success || jp.success ? eu : eu;
  },

  /**
   * 初始化商品历史数据（首次部署用）
   * 调 /api/macro/fetch/commodities/history
   */
  initCommoditiesHistory: async (): Promise<UpdateResponse> => {
    return directClient.post<UpdateResponse>('/api/macro/fetch/commodities/history');
  },

  /**
   * 更新美债 + 汇率 + 中国 10y（前端中美利差/汇率 tab 用，并发请求）
   * 三个端点并发，任一成功即视为成功
   */
  updateUsTreasuriesAndRates: async (): Promise<UpdateResponse> => {
    const [us, fx, cn] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/update/us-treasuries'),
      directClient.post<UpdateResponse>('/api/macro/update/exchange-rates'),
      directClient.post<UpdateResponse>('/api/macro/update/china-bonds'),
    ]);
    return us.success || fx.success || cn.success ? us : fx;
  },

  /**
   * 更新德债 + 日债（前端德债/日债 tab 用，并发请求）
   */
  updateBonds: async (): Promise<UpdateResponse> => {
    const [eu, jp] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/update/eu-bonds'),
      directClient.post<UpdateResponse>('/api/macro/update/jp-bonds'),
    ]);
    return eu.success || jp.success ? eu : eu;
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
   * 并发调 vix + tga + hibor 三个 history 端点（参考 initBondsHistory 模式）
   * 任一成功即视为成功
   */
  initLiquidityHistory: async (): Promise<UpdateResponse> => {
    const [vix, tga, hibor] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/fetch/vix/history'),
      directClient.post<UpdateResponse>('/api/macro/fetch/tga/history'),
      directClient.post<UpdateResponse>('/api/macro/fetch/hibor/history'),
    ]);
    return vix.success || tga.success || hibor.success ? vix : vix;
  },

  /**
   * 增量更新流动性/风险数据（最近 7 天）
   * 并发调 vix + tga + hibor 三个 update 端点
   * 任一成功即视为成功
   */
  updateLiquidity: async (): Promise<UpdateResponse> => {
    const [vix, tga, hibor] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/update/vix'),
      directClient.post<UpdateResponse>('/api/macro/update/tga'),
      directClient.post<UpdateResponse>('/api/macro/update/hibor'),
    ]);
    return vix.success || tga.success || hibor.success ? vix : vix;
  },

  /**
   * 初始化利率利差历史数据（首次部署用）
   * 并发调 china-bonds + ted-spread 两个 history 端点
   * 任一成功即视为成功（与 initBondsHistory 同模式）
   */
  initRatesHistory: async (): Promise<UpdateResponse> => {
    const [cn, ted] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/fetch/china-bonds/history'),
      directClient.post<UpdateResponse>('/api/macro/fetch/ted-spread/history'),
    ]);
    return cn.success || ted.success ? cn : cn;
  },

  /**
   * 增量更新利率利差数据（最近 7 天）
   * 并发调 china-bonds + ted-spread 两个 update 端点
   * 任一成功即视为成功
   */
  updateRates: async (): Promise<UpdateResponse> => {
    const [cn, ted] = await Promise.all([
      directClient.post<UpdateResponse>('/api/macro/update/china-bonds'),
      directClient.post<UpdateResponse>('/api/macro/update/ted-spread'),
    ]);
    return cn.success || ted.success ? cn : cn;
  },
};