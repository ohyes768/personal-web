/**
 * API 类型定义
 */

// 通用 API 响应类型
export interface ApiResponse<T = any> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
}

// 经济数据类型
export interface ExchangeRateData {
  date: string;
  dollar_index: number;
  usd_cny: number;
  usd_jpy: number;
  usd_eur: number;
}

// 新闻分析类型
export interface PolicyRankingData {
  board_code: string;
  board_name: string;
  board_type: string;
  policy_score: number;
  recommendation_grade: string;
  bullish_ratio: number;
  avg_importance: number;
}

export interface SentimentDistribution {
  bullish: number;
  bearish: number;
  neutral: number;
}

// 抖音视频类型
export interface VideoInfo {
  aweme_id: string;
  status: string;
  title: string;
  author: string;
  description?: string;
  audio_url: string;
  transcript?: TranscriptInfo;
  processed_at?: number;
  upload_time?: string;
  error?: string;
}

export interface TranscriptInfo {
  text: string;
  segments?: Array<{
    start_time: number;
    end_time: number;
    text: string;
    confidence: number;
  }>;
  confidence: number;
  audio_duration: number;
}

export interface VideoListResponse {
  total_count: number;
  videos: VideoInfo[];
  page: number;
  page_size: number;
}
