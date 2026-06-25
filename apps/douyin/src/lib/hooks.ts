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
 * v2.0: status 参数走服务端过滤，不再做客户端二次过滤
 */
export function useDouyinVideos(activeTab: TabType) {
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVideos = useCallback(async (isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await douyinApi.getVideos({
        status: activeTab,
      });

      setVideos(data.videos || []);
      setTotalCount(data.total_count ?? data.videos?.length ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取数据失败');
      console.error('Error fetching videos:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  return {
    videos,
    totalCount,
    loading,
    refreshing,
    error,
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
    setProcessMessage('正在启动 ASR 处理...');
    let nextMessageDelay = 3000;
    try {
      const res = await douyinApi.processAsync();
      const pending = res?.data?.pending ?? 0;
      if (!res?.success) {
        // 已有任务在跑 / 后端拒绝
        setProcessMessage(res?.message || '已有处理任务在进行中');
      } else if (pending === 0) {
        setProcessMessage('没有待处理的视频');
      } else {
        setProcessMessage(
          `已启动 ASR 处理 ${pending} 个视频（后台串行运行，请稍后刷新查看结果）`,
        );
        // 启动成功时延长提示停留时间
        nextMessageDelay = 5000;
      }
    } catch (err) {
      setProcessMessage('启动处理失败，请检查后端日志');
      console.error('启动 ASR 处理失败:', err);
    }
    setTimeout(() => {
      setProcessing(false);
      setProcessMessage('');
      onComplete?.();
    }, nextMessageDelay);
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