/**
 * Douyin 模块自定义 Hooks
 * 封装组件中可复用的状态逻辑
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { douyinApi } from './api';
import type {
  VideoInfo,
  VideoListResponse,
  StatsResponse,
  ProcessTaskResponse,
  TabType,
} from './types';

/**
 * 视频列表 Hook
 */
export function useDouyinVideos(page: number, pageSize: number, activeTab: TabType) {
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  const fetchVideos = useCallback(async (isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await douyinApi.getVideos({
        page,
        page_size: pageSize,
        is_read: activeTab === 'read' ? true : undefined,
      });

      // 客户端二次过滤（兼容 v2.0 status=unread 与 旧 is_read=false）
      let filteredVideos = data.videos || [];
      if (activeTab === 'unread') {
        filteredVideos = filteredVideos.filter(
          (v) => v.status === 'unread' || (v.status === 'completed' && !v.is_read),
        );
      } else if (activeTab === 'read') {
        filteredVideos = filteredVideos.filter(
          (v) => v.status === 'read' || v.is_read === true,
        );
      }

      setVideos(filteredVideos);
      setTotal(filteredVideos.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取数据失败');
      console.error('Error fetching videos:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, pageSize, activeTab]);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  return {
    videos,
    loading,
    refreshing,
    error,
    total,
    refetch: fetchVideos,
  };
}

/**
 * 待处理数量 Hook
 */
export function usePendingCount() {
  const [pendingCount, setPendingCount] = useState(0);

  const fetchPendingCount = useCallback(async () => {
    try {
      const data = await douyinApi.getStats();
      setPendingCount(data.pending || 0);
    } catch (err) {
      console.error('Error fetching pending count:', err);
    }
  }, []);

  useEffect(() => {
    fetchPendingCount();
  }, [fetchPendingCount]);

  return {
    pendingCount,
    refetch: fetchPendingCount,
  };
}

/**
 * 异步处理 Hook
 * 包含轮询进度功能
 */
export function useAsyncProcess(onComplete?: () => void) {
  const [processing, setProcessing] = useState(false);
  const [processMessage, setProcessMessage] = useState<string>('');
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const startProcess = useCallback(async () => {
    // v2.0 流程：处理由 douyin-collector 自动推送，前端不再触发
    // 保留此函数仅做"刷新列表"语义
    setProcessing(true);
    setProcessMessage('刷新待处理列表（处理由 douyin-collector 自动推送）');
    try {
      await douyinApi.processAsync();
    } catch {
      // 忽略错误（旧接口已 stub 化）
    }
    setTimeout(() => {
      setProcessing(false);
      setProcessMessage('');
      onComplete?.();
    }, 500);
  }, [onComplete]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  return {
    processing,
    processMessage,
    progress,
    startProcess,
  };
}

/**
 * 视频操作 Hook
 */
export function useVideoActions(onSuccess?: () => void) {
  const [loading, setLoading] = useState(false);

  const markAsRead = useCallback(async (videoId: string, isRead: boolean) => {
    setLoading(true);
    try {
      await douyinApi.markAsRead(videoId, { is_read: isRead });
      onSuccess?.();
    } catch (err) {
      console.error('标记已读失败:', err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [onSuccess]);

  const deleteRecord = useCallback(async (videoId: string) => {
    setLoading(true);
    try {
      await douyinApi.deleteRecord(videoId);
      onSuccess?.();
    } catch (err) {
      console.error('删除记录失败:', err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [onSuccess]);

  const deleteWithFile = useCallback(async (videoId: string) => {
    setLoading(true);
    try {
      await douyinApi.deleteWithFile(videoId);
      onSuccess?.();
    } catch (err) {
      console.error('删除失败:', err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [onSuccess]);

  return {
    loading,
    markAsRead,
    deleteRecord,
    deleteWithFile,
  };
}

/**
 * 视频详情 Hook
 */
export function useVideoDetail() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async (videoId: string): Promise<VideoInfo | null> => {
    setLoading(true);
    setError(null);

    try {
      const detail = await douyinApi.getVideoDetail(videoId);
      return detail;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '获取详情失败';
      setError(errorMessage);
      console.error('获取视频详情失败:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    loading,
    error,
    fetchDetail,
  };
}

/**
 * 工具函数 Hook
 */
export function useDouyinUtils() {
  const formatTime = useCallback((timestamp: number | string | undefined): string => {
    if (!timestamp) return '未知';
    if (typeof timestamp === 'number') {
      return new Date(timestamp * 1000).toLocaleString('zh-CN');
    }
    return new Date(timestamp).toLocaleString('zh-CN');
  }, []);

  const formatSegmentTime = useCallback((seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }, []);

  return {
    formatTime,
    formatSegmentTime,
  };
}