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
  SchedulerJob,
  SchedulerJobRun,
} from './types';

export const douyinApi = {
  /**
   * 获取视频列表
   * 后端默认过滤掉 pending/deleted，返回 read+unread+processing+failed 混合列表
   */
  getVideos: (params: VideoListParams = {}): Promise<VideoListResponse> =>
    directClient.get<VideoListResponse>('/api/douyin/videos', {
      page: params.page ?? 1,
      page_size: params.page_size ?? 100,
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

/**
 * scheduler 管理 API（/api/scheduler/*，后端 src/scheduler/routes.py）
 * 与 dividend/macro 的 schedulerApi 同形：jobs 列表 / 启停 / 立即执行 / 历史
 */
export const schedulerApi = {
  listJobs: (): Promise<{ jobs: SchedulerJob[] }> =>
    directClient.get<{ jobs: SchedulerJob[] }>('/api/douyin/scheduler/jobs'),

  setEnabled: (jobId: string, enabled: boolean): Promise<SchedulerJob> =>
    directClient.patch<SchedulerJob>(`/api/douyin/scheduler/jobs/${jobId}`, { enabled }),

  runNow: (jobId: string): Promise<{ job_id: string; triggered_at: string }> =>
    directClient.post(`/api/douyin/scheduler/jobs/${jobId}/run`),

  getRuns: (jobId: string, limit = 20): Promise<{ runs: SchedulerJobRun[] }> =>
    directClient.get<{ runs: SchedulerJobRun[] }>(
      `/api/douyin/scheduler/jobs/${jobId}/runs?limit=${limit}`
    ),
};