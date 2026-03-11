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

      // 未读 Tab：前端过滤，只显示 completed 且 is_read=false 的视频
      let filteredVideos = data.videos || [];
      if (activeTab === 'unread') {
        filteredVideos = filteredVideos.filter((v) => !v.is_read);
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
    setProcessing(true);
    setProcessMessage('正在启动处理任务...');
    setProgress({ current: 0, total: 0 });

    try {
      const response = await douyinApi.processAsync();

      if (response.success) {
        const totalTasks = response.data?.pending || 0;
        setProgress({ current: 0, total: totalTasks });
        setProcessMessage(`后台处理已启动，待处理 ${totalTasks} 个视频`);

        // 记录开始时的已完成数量
        let initialCompleted = 0;
        let initialFailed = 0;

        try {
          const initialStats = await douyinApi.getStats();
          initialCompleted = initialStats.completed || 0;
          initialFailed = initialStats.failed || 0;
        } catch (err) {
          console.error('获取初始状态失败:', err);
        }

        // 轮询获取进度
        pollingIntervalRef.current = setInterval(async () => {
          try {
            const statsData = await douyinApi.getStats();
            const { completed, failed, processing: proc, pending: currentPending } = statsData;

            // 计算本次完成的数量
            const currentProcessed = (completed - initialCompleted) + (failed - initialFailed);
            setProgress({ current: currentProcessed, total: totalTasks });
            setProcessMessage(`处理中... 已完成（${currentProcessed}/${totalTasks}）`);

            // 处理完成
            if (proc === 0 && currentPending === 0) {
              if (pollingIntervalRef.current) {
                clearInterval(pollingIntervalRef.current);
                pollingIntervalRef.current = null;
              }
              setProcessing(false);
              setProcessMessage('');
              onComplete?.();
            }
          } catch (err) {
            console.error('轮询进度失败:', err);
          }
        }, 2000);
      } else {
        setProcessMessage(response.message || '处理任务启动失败');
        setTimeout(() => {
          setProcessing(false);
          setProcessMessage('');
        }, 3000);
      }
    } catch (err) {
      setProcessMessage(err instanceof Error ? err.message : '启动处理失败');
      setTimeout(() => {
        setProcessing(false);
        setProcessMessage('');
      }, 3000);
    }
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

