"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8070';

interface VideoItem {
  aweme_id: string;
  status: string;
  title: string;
  author: string;
  description?: string;
  audio_url: string;
  transcript?: {
    text: string;
    segments?: Array<{
      start_time: number;
      end_time: number;
      text: string;
      confidence: number;
    }>;
    confidence: number;
    audio_duration: number;
  };
  processed_at?: number;
  upload_time?: string;
  error?: string;
  is_read?: boolean;
  read_at?: number;
}

interface VideoListResponse {
  total_count: number;
  videos: VideoItem[];
  page: number;
  page_size: number;
}

interface StatsResponse {
  total: number;
  completed: number;
  processing: number;
  failed: number;
  pending: number;
  success_rate: number;
}

type TabType = 'unread' | 'read';

export default function DouyinPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processMessage, setProcessMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);

  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('unread');

  // Modal 状态
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const pageSize = 20;

  // 获取待处理数量
  const fetchPendingCount = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/stats`);
      if (response.ok) {
        const data: StatsResponse = await response.json();
        setPendingCount(data.pending || 0);
      }
    } catch (err) {
      console.error("Error fetching pending count:", err);
    }
  };

  const fetchVideos = async (isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      // 根据当前 Tab 构建请求参数
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString()
      });

      let apiUrl = '';
      if (activeTab === 'read') {
        params.append('is_read', 'true');
      }

      apiUrl = `${API_BASE_URL}/api/douyin/videos?${params}`;

      const response = await fetch(apiUrl);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: VideoListResponse = await response.json();

      // 未读 Tab：前端过滤，只显示 completed 且 is_read=false 的视频
      //（pending 视频已被后端过滤）
      let filteredVideos = data.videos || [];
      if (activeTab === 'unread') {
        filteredVideos = filteredVideos.filter((v) => !v.is_read);
      }

      setVideos(filteredVideos);
      setTotal(filteredVideos.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取数据失败");
      console.error("Error fetching videos:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleProcess = async () => {
    setProcessing(true);
    setProcessMessage("正在启动处理任务...");

    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/process/async`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (data.success) {
        const { pending: totalTasks } = data.data || {};
        setProcessMessage(`后台处理已启动，待处理 ${totalTasks} 个视频`);

        // 记录开始时的已完成数量
        let initialCompleted = 0;
        let initialFailed = 0;

        // 获取初始状态（等待完成）
        try {
          const initialStats = await fetch(`${API_BASE_URL}/api/douyin/stats`);
          if (initialStats.ok) {
            const initialData: StatsResponse = await initialStats.json();
            initialCompleted = initialData.completed || 0;
            initialFailed = initialData.failed || 0;
          }
        } catch (err) {
          console.error("获取初始状态失败:", err);
        }

        // 轮询获取进度
        const pollInterval = setInterval(async () => {
          try {
            const statsRes = await fetch(`${API_BASE_URL}/api/douyin/stats`);
            if (statsRes.ok) {
              const statsData: StatsResponse = await statsRes.json();
              const { completed, failed, processing, pending: currentPending } = statsData;

              // 计算本次完成的数量
              const currentProcessed = (completed - initialCompleted) + (failed - initialFailed);

              setProcessMessage(`处理中... 已完成（${currentProcessed}/${totalTasks}）`);

              // 更新待处理数量
              setPendingCount(currentPending || 0);

              // 处理完成
              if (processing === 0 && currentPending === 0) {
                clearInterval(pollInterval);
                setTimeout(() => {
                  setProcessing(false);
                  setProcessMessage("");
                  setPage(1);
                  fetchVideos(true);
                }, 1000);
              }
            }
          } catch (err) {
            console.error("轮询进度失败:", err);
          }
        }, 2000); // 每 2 秒轮询一次
      } else {
        setProcessMessage(data.message || "处理任务启动失败");
        setTimeout(() => {
          setProcessing(false);
          setProcessMessage("");
        }, 3000);
      }
    } catch (err) {
      setProcessMessage(err instanceof Error ? err.message : "启动处理失败");
      setTimeout(() => {
        setProcessing(false);
        setProcessMessage("");
      }, 3000);
    }
  };

  // 标记已读
  const handleMarkAsRead = async (videoId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/videos/${videoId}/read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_read: true })
      });

      if (response.ok) {
        // 标记成功后刷新列表并关闭弹框
        setSelectedVideo(null);
        fetchVideos(true);
      }
    } catch (err) {
      console.error('标记已读失败:', err);
    }
  };

  // 删除记录（仅删除 douyin-processor 记录，不删除 file-system-go 文件）
  const handleDeleteRecord = async (videoId: string) => {
    if (!confirm('确定要删除记录吗？（保留原始文件）')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/videos/${videoId}?keep_file=true`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setSelectedVideo(null);
        fetchVideos(true);
      }
    } catch (err) {
      console.error('删除记录失败:', err);
    }
  };

  // 删除记录并取消收藏（删除 douyin-processor 记录 + file-system-go 文件）
  const handleDelete = async (videoId: string) => {
    if (!confirm('确定要删除记录并取消收藏吗？此操作将删除原始文件，无法撤销！')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/videos/${videoId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setSelectedVideo(null);
        fetchVideos(true);
      }
    } catch (err) {
      console.error('删除失败:', err);
    }
  };

  // 打开视频详情弹框
  const openVideoDetail = async (video: VideoItem) => {
    setSelectedVideo(video);
    setModalError(null);

    // 如果没有详细信息，先获取详情
    if (!video.transcript && video.status === "completed") {
      setModalLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/douyin/videos/${video.aweme_id}`);
        if (response.ok) {
          const detailData: VideoItem = await response.json();
          setSelectedVideo(detailData);
        } else {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
      } catch (err) {
        setModalError(err instanceof Error ? err.message : "获取详情失败");
      } finally {
        setModalLoading(false);
      }
    }
  };

  // 关闭弹框
  const closeModal = () => {
    setSelectedVideo(null);
    setModalError(null);
  };

  // Tab 切换
  const handleTabChange = (newTab: TabType) => {
    setActiveTab(newTab);
    setPage(1);
  };

  // 页面加载时并行获取待处理数量和视频列表
  useEffect(() => {
    fetchPendingCount();
    fetchVideos();
  }, [page, activeTab]);

  // 格式化时间
  const formatTime = (timestamp: number | string | undefined) => {
    if (!timestamp) return "未知";
    if (typeof timestamp === 'number') {
      return new Date(timestamp * 1000).toLocaleString("zh-CN");
    }
    return new Date(timestamp).toLocaleString("zh-CN");
  };

  // 格式化时间段（秒数 -> MM:SS 格式）
  const formatSegmentTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // 状态标签
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return (
          <span className="px-3 py-1 bg-green-900/50 text-green-300 text-sm rounded-full whitespace-nowrap">
            已识别
          </span>
        );
      case "processing":
        return (
          <span className="px-3 py-1 bg-yellow-900/50 text-yellow-300 text-sm rounded-full whitespace-nowrap">
            识别中
          </span>
        );
      case "failed":
        return (
          <span className="px-3 py-1 bg-red-900/50 text-red-300 text-sm rounded-full whitespace-nowrap">
            识别失败
          </span>
        );
      case "pending":
        return (
          <span className="px-3 py-1 bg-gray-700/50 text-gray-300 text-sm rounded-full whitespace-nowrap">
            待处理
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto p-8">
        {/* 头部导航 */}
        <div className="mb-8">
          <div className="flex justify-between items-start">
            <div>
              <Link
                href="/"
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4">抖音视频文字稿</h1>
            </div>
            <div className="text-right flex items-center gap-2">
              <button
                onClick={handleProcess}
                disabled={processing || loading || refreshing}
                className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
                  pendingCount > 0
                    ? "bg-orange-600 hover:bg-orange-700"
                    : "bg-gray-700 hover:bg-gray-600"
                } disabled:bg-gray-800 disabled:cursor-not-allowed`}
                title={pendingCount > 0 ? `处理 ${pendingCount} 个待处理视频` : "没有待处理的视频"}
              >
                <svg
                  className={`w-5 h-5 ${processing ? "animate-spin" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                {processing ? "处理中..." : `待处理 (${pendingCount})`}
              </button>
              <div className="group relative">
                <svg
                  className="w-5 h-5 text-gray-400 cursor-help"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-gray-800 border border-gray-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10">
                  <p className="text-gray-300 text-sm">
                    点击处理所有待处理的音频文件，后台异步执行 ASR 识别
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 处理状态提示 */}
          {processMessage && (
            <div className="mt-4 p-4 bg-blue-900/50 border border-blue-700 rounded-lg">
              <p className="text-blue-200">{processMessage}</p>
            </div>
          )}
        </div>

        {/* Tab 切换 */}
        <div className="mb-6">
          <div className="flex gap-1">
            <button
              onClick={() => handleTabChange('unread')}
              className={`px-6 py-2 rounded-l-lg transition-colors ${
                activeTab === 'unread'
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              未读
            </button>
            <button
              onClick={() => handleTabChange('read')}
              className={`px-6 py-2 rounded-r-lg transition-colors ${
                activeTab === 'read'
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              已读
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-8 p-4 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-200">错误: {error}</p>
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <p className="mt-4 text-gray-400">加载中...</p>
          </div>
        )}

        {/* 视频列表 */}
        {!loading && videos && videos.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-6 mb-8">
              {videos.map((video) => (
                <div
                  key={video.aweme_id}
                  onClick={() => openVideoDetail(video)}
                  className="relative group p-6 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors border border-gray-800 cursor-pointer"
                >
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold flex-1 pr-4">
                      {video.title || "未知标题"}
                    </h3>
                    <div className="flex items-center gap-2">
                      {/* 未读 Tab 且状态为 completed 时不显示状态标识 */}
                      {(activeTab !== 'unread' || video.status !== 'completed') && renderStatusBadge(video.status)}
                      {/* 已读视频显示两个删除选项 */}
                      {activeTab === 'read' && video.is_read && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteRecord(video.aweme_id);
                            }}
                            className="p-1 bg-gray-600 hover:bg-gray-700 rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="删除记录"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(video.aweme_id);
                            }}
                            className="p-1 bg-red-600 hover:bg-red-700 rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="删除并取消收藏"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </>
                      )}
                      {/* 未读视频显示变为已读和删除记录按钮 */}
                      {activeTab === 'unread' && !video.is_read && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleMarkAsRead(video.aweme_id);
                            }}
                            className="p-1 bg-green-600 hover:bg-green-700 rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="标记已读"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteRecord(video.aweme_id);
                            }}
                            className="p-1 bg-gray-600 hover:bg-gray-700 rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="删除记录"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  <p className="text-gray-400 mb-2">
                    作者: {video.author || "未知"}
                  </p>

                  <p className="text-gray-600 text-sm">
                    {video.upload_time ? new Date(video.upload_time).toLocaleString() : "未知时间"}
                  </p>
                </div>
              ))}
            </div>

            {/* 分页 */}
            {total > pageSize && (
              <div className="flex justify-center gap-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  上一页
                </button>
                <span className="px-4 py-2 text-gray-400">
                  第 {page} 页，共 {Math.ceil(total / pageSize)} 页
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= Math.ceil(total / pageSize)}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}

        {/* 空状态 */}
        {!loading && videos.length === 0 && !error && (
          <div className="text-center py-12">
            <p className="text-gray-400 text-lg">
              {activeTab === 'unread' ? '暂无未读视频' : '暂无已读视频'}
            </p>
          </div>
        )}
      </div>

      {/* 视频详情弹框 */}
      {selectedVideo && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={closeModal}
        >
          {/* 背景遮罩 */}
          <div className="absolute inset-0 bg-black/80 backdrop-blur-sm"></div>

          {/* 弹框内容 */}
          <div
            className="relative bg-gray-900 rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 */}
            <div className="flex items-center justify-between p-6 border-b border-gray-800">
              <h2 className="text-2xl font-bold flex-1 pr-4 line-clamp-2">
                {selectedVideo.title || "未知标题"}
              </h2>
              <button
                onClick={closeModal}
                className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* 内容区域 */}
            <div className="flex-1 overflow-y-auto p-6">
              {modalLoading ? (
                <div className="text-center py-12">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
                  <p className="mt-4 text-gray-400">加载详情中...</p>
                </div>
              ) : modalError ? (
                <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
                  <p className="text-red-200">错误: {modalError}</p>
                </div>
              ) : selectedVideo.status === "failed" ? (
                <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
                  <p className="text-red-300">识别失败: {selectedVideo.error || "未知错误"}</p>
                </div>
              ) : selectedVideo.status === "pending" || selectedVideo.status === "processing" ? (
                <div className="p-6 bg-blue-900/50 border border-blue-700 rounded-lg">
                  <p className="text-blue-200">
                    {selectedVideo.status === "processing"
                      ? "视频正在识别中，请稍后再来查看"
                      : "视频尚未处理，请在列表页点击\"处理待处理\"按钮"}
                  </p>
                </div>
              ) : (
                <>
                  {/* 视频信息 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 p-4 bg-gray-800/50 rounded-lg">
                    <div>
                      <p className="text-gray-400 text-sm mb-1">作者</p>
                      <p className="text-lg">{selectedVideo.author || "未知"}</p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">上传时间</p>
                      <p className="text-lg">{formatTime(selectedVideo.upload_time)}</p>
                    </div>
                    {selectedVideo.transcript && (
                      <>
                        <div>
                          <p className="text-gray-400 text-sm mb-1">音频时长</p>
                          <p className="text-lg">
                            {selectedVideo.transcript.audio_duration.toFixed(2)} 秒
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm mb-1">识别置信度</p>
                          <p className="text-lg">
                            {(selectedVideo.transcript.confidence * 100).toFixed(1)}%
                          </p>
                        </div>
                      </>
                    )}
                  </div>

                  {/* 描述 */}
                  {selectedVideo.description && selectedVideo.description !== selectedVideo.title && (
                    <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
                      <p className="text-gray-400 text-sm mb-2">视频描述</p>
                      <p className="text-gray-200">{selectedVideo.description}</p>
                    </div>
                  )}

                  {/* 文字稿内容 */}
                  {selectedVideo.transcript ? (
                    <div className="bg-gray-800/50 rounded-lg p-6">
                      <h3 className="text-xl font-bold mb-4">识别文字稿</h3>

                      {/* 分段信息（如果有分段） */}
                      {selectedVideo.transcript.segments && selectedVideo.transcript.segments.length > 0 ? (
                        <div className="space-y-3">
                          {selectedVideo.transcript.segments.map((segment, index) => (
                            <div key={index} className="flex gap-4 text-sm">
                              <span className="text-gray-500 whitespace-nowrap select-none">
                                [{formatSegmentTime(segment.start_time)} - {formatSegmentTime(segment.end_time)}]
                              </span>
                              <span className="text-gray-300 flex-1">
                                {segment.text}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <p className="text-gray-200 leading-loose text-base whitespace-pre-wrap">
                            {selectedVideo.transcript.text}
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="bg-gray-800/50 rounded-lg p-6">
                      <p className="text-gray-400">暂无文字稿</p>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* 底部操作栏 */}
            <div className="p-4 border-t border-gray-800 flex justify-between items-center">
              <div className="flex gap-2">
                {/* 未读视频显示标记已读和删除记录按钮 */}
                {!selectedVideo.is_read && selectedVideo.status === 'completed' && (
                  <>
                    <button
                      onClick={() => handleMarkAsRead(selectedVideo.aweme_id)}
                      className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      标记已读
                    </button>
                    <button
                      onClick={() => handleDeleteRecord(selectedVideo.aweme_id)}
                      className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      删除记录
                    </button>
                  </>
                )}
                {/* 已读视频显示删除记录和删除并取消收藏按钮 */}
                {selectedVideo.is_read && (
                  <>
                    <button
                      onClick={() => handleDeleteRecord(selectedVideo.aweme_id)}
                      className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      删除记录
                    </button>
                    <button
                      onClick={() => handleDelete(selectedVideo.aweme_id)}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      删除并取消收藏
                    </button>
                  </>
                )}
              </div>
              <button
                onClick={closeModal}
                className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
