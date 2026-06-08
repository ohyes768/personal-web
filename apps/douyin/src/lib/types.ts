/**
 * Douyin 模块类型定义
 */

// 视频状态类型
export type VideoStatus = 'pending' | 'processing' | 'completed' | 'failed';

// Tab 类型
export type TabType = 'unread' | 'read';

// 转写分段信息
export interface TranscriptSegment {
  start_time: number;
  end_time: number;
  text: string;
  confidence: number;
}

// 转写信息
export interface TranscriptInfo {
  text: string;
  segments?: TranscriptSegment[];
  confidence: number;
  audio_duration: number;
}

// 视频信息
export interface VideoInfo {
  aweme_id: string;
  status: VideoStatus;
  title: string;
  author: string;
  description?: string;
  audio_url: string;
  transcript?: TranscriptInfo;
  processed_at?: number;
  upload_time?: string;
  error?: string;
  is_read?: boolean;
  read_at?: number;
}

// 视频列表响应
export interface VideoListResponse {
  total_count: number;
  videos: VideoInfo[];
  page: number;
  page_size: number;
}

// 统计信息
export interface StatsResponse {
  total: number;
  completed: number;
  processing: number;
  failed: number;
  pending: number;
  success_rate: number;
}

// 处理任务响应
export interface ProcessTaskResponse {
  success: boolean;
  message?: string;
  data?: {
    pending?: number;
  };
}

// 列表查询参数
export interface VideoListParams {
  page?: number;
  page_size?: number;
  is_read?: boolean;
}

// 标记已读 DTO
export interface MarkAsReadDto {
  is_read: boolean;
}