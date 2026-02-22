/**
 * 新闻分析 API 封装
 */
import { apiClient } from './client';
import type { PolicyRankingData, SentimentDistribution } from './types';

export const newsApi = {
  /**
   * 获取政策推荐指数排行榜
   */
  getPolicyRanking: (timeRange: string = '1M', topN: number = 20) =>
    apiClient.get<PolicyRankingData[]>('/api/news/policy-ranking', {
      time_range: timeRange,
      top_n: topN
    }),

  /**
   * 获取情感分布数据
   */
  getSentimentDistribution: (timeRange: string = '1M') =>
    apiClient.get<SentimentDistribution>('/api/news/sentiment-distribution', {
      time_range: timeRange
    }),

  /**
   * 获取板块影响数据
   */
  getSectorImpact: (date: string) =>
    apiClient.get(`/api/news/sector-impact/${date}`),

  /**
   * 获取板块热力图数据
   */
  getHeatmap: (boardCode: string, timeRange: string = '1M') =>
    apiClient.get('/api/news/heatmap', {
      board_code: boardCode,
      time_range: timeRange
    }),
};
