/**
 * Douyin 模块 API 封装
 * 所有 Douyin 相关 API 调用必须通过此文件
 */
import { directClient } from './api-client';
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
   * v2.0: 用 status=unread|read 服务端过滤（替代旧的 is_read 客户端二次过滤）
   */
  getVideos: (params: VideoListParams = {}): Promise<VideoListResponse> =>
    directClient.get<VideoListResponse>('/api/douyin/videos', {
      page: params.page ?? 1,
      page_size: params.page_size ?? 100,
      ...(params.status ? { status: params.status } : {}),
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
   * 触发后端处理 status=pending 的视频
   * 后端 fire-and-forget：立即返回 + 后台串行调阿里 ASR + mark_processed
   * 已有任务在跑会返回 success=false（前端据此提示）
   */
  processAsync: (): Promise<ProcessTaskResponse> =>
    directClient.post<ProcessTaskResponse>('/api/douyin/process/pending', {}),

  /**
   * 标记已读/未读（v2.0: 路径从 /api/douyin/videos/{id}/read 改为 /api/aweme/{id}/read）
   */
  markAsRead: (videoId: string, data: MarkAsReadDto): Promise<void> =>
    directClient.post<void>(`/api/aweme/${videoId}/read`, data),

  /**
   * 删除记录（仅删除 douyin-processor 记录，保留原始文件）
   * v2.0: 路径改为 /api/aweme/{id}
   */
  deleteRecord: (videoId: string): Promise<void> =>
    directClient.delete<void>(`/api/aweme/${videoId}`, { keep_file: 'true' }),

  /**
   * 删除记录并取消收藏（删除 douyin-processor 记录 + 原始文件）
   * v2.0: 路径改为 /api/aweme/{id}
   */
  deleteWithFile: (videoId: string): Promise<void> =>
    directClient.delete<void>(`/api/aweme/${videoId}`),
};