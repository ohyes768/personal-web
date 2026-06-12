/**
 * Douyin 模块类型定义
 */

// 视频状态类型（v2.0 流程：已读/未读并入 status 字段）
// 旧值（pending/processing/completed/failed）保留以兼容未迁移的 status.json 数据
export type VideoStatus =
  | 'pending'      // v2.0: 待处理（douyin-collector 推过来的新记录）
  | 'unread'       // v2.0: ASR 完成、用户未读
  | 'read'         // v2.0: 用户已读
  | 'deleted'      // v2.0: 用户主动删
  // 旧值（迁移前过渡期）
  | 'processing'
  | 'completed'
  | 'failed';

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
  upload_time?: string;             // 推到 douyin-processor 的时间（v2.0 mark_pending 写入；旧数据为空）
  video_publish_time?: string;     // 原抖音平台发布时间（v2.0 douyin-collector 推过来时存）
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