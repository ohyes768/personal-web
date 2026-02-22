/**
 * 抖音视频 API 封装
 */
import { apiClient } from './client';
import type { VideoInfo, VideoListResponse } from './types';

export const douyinApi = {
  /**
   * 获取视频列表
   */
  getVideos: (page: number = 1, pageSize: number = 20) =>
    apiClient.get<VideoListResponse>('/api/douyin/videos', {
      page,
      page_size: pageSize
    }),

  /**
   * 获取视频详情
   */
  getVideoDetail: (videoId: string) =>
    apiClient.get<VideoInfo>(`/api/douyin/videos/${videoId}`),

  /**
   * 搜索视频
   */
  searchVideos: (keyword: string, page: number = 1, pageSize: number = 20) =>
    apiClient.get<VideoListResponse>('/api/douyin/search', {
      keyword,
      page,
      page_size: pageSize
    }),
};
