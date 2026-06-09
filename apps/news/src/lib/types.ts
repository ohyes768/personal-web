/**
 * News 模块类型定义
 */

/** 政策推荐排行数据 */
export interface PolicyRankingData {
  board_code: string;
  board_name: string;
  board_type: string;
  policy_score: number;
  recommendation_grade: string;
  bullish_ratio: number;
  avg_importance: number;
}

/** 情感分布数据 */
export interface SentimentDistribution {
  bullish: number;
  bearish: number;
  neutral: number;
}

/** 板块影响数据 */
export interface SectorImpactData {
  board_code: string;
  board_name: string;
  impact_score: number;
  affected_sectors: string[];
}

/** 热力图数据 */
export interface HeatmapData {
  board_code: string;
  board_name: string;
  impact_value: number;
  timestamp: string;
}

/** 板块热力图响应 */
export interface HeatmapResponse {
  data: HeatmapData[];
  time_range: string;
}

/** 查询参数 */
export interface NewsQueryParams {
  time_range?: string;
  top_n?: number;
  board_code?: string;
  date?: string;
}