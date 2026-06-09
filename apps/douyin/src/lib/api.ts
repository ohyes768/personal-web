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
   * v2.0 流程：处理改由 douyin-collector 主动推送，本接口已弃用
   * 保留返回结构兼容旧调用方，实际 do-nothing + 提示
   */
  processAsync: (): Promise<ProcessTaskResponse> =>
    Promise.resolve({
      success: true,
      message: '处理已改为 douyin-collector 自动推送模式',
      data: { pending: 0 },
    }),

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