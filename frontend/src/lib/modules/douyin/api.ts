/**
 * Douyin 模块 API 封装
 * 所有 Douyin 相关 API 调用必须通过此文件
 */
import { directClient } from '@/lib/api/client';
import type {
  VideoInfo,
  VideoListResponse,
  StatsResponse,
  ProcessTaskResponse,
  VideoListParams,
  MarkAsReadDto,
} from './types';

export const douyinApi = {
  /**
   * 获取视频列表
   */
  getVideos: (params: VideoListParams = {}): Promise<VideoListResponse> =>
    directClient.get<VideoListResponse>('/api/douyin/videos', {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      ...(params.is_read !== undefined ? { is_read: params.is_read } : {}),
    }),

  /**
   * 获取视频详情
   */
  getVideoDetail: (videoId: string): Promise<VideoInfo> =>
    directClient.get<VideoInfo>(`/api/douyin/videos/${videoId}`),

  /**
   * 获取统计信息
   */
  getStats: (): Promise<StatsResponse> =>
    directClient.get<StatsResponse>('/api/douyin/stats'),

  /**
   * 异步处理所有待处理视频
   */
  processAsync: (): Promise<ProcessTaskResponse> =>
    directClient.post<ProcessTaskResponse>('/api/douyin/process/async'),

  /**
   * 标记已读/未读
   */
  markAsRead: (videoId: string, data: MarkAsReadDto): Promise<void> =>
    directClient.post<void>(`/api/douyin/videos/${videoId}/read`, data),

  /**
   * 删除记录（仅删除 douyin-processor 记录，保留原始文件）
   */
  deleteRecord: (videoId: string): Promise<void> =>
    directClient.delete<void>(`/api/douyin/videos/${videoId}`, { keep_file: 'true' }),

  /**
   * 删除记录并取消收藏（删除 douyin-processor 记录 + 原始文件）
   */
  deleteWithFile: (videoId: string): Promise<void> =>
    directClient.delete<void>(`/api/douyin/videos/${videoId}`),
};