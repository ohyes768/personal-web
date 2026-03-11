'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { Tabs } from '@/components/ui/Tabs';
import { Loading } from '@/components/ui/Loading';
import { VideoCard } from '@/components/modules/douyin/VideoCard';
import { VideoModal } from '@/components/modules/douyin/VideoModal';
import { useDouyinVideos, usePendingCount, useAsyncProcess, useVideoActions } from '@/lib/modules/douyin/hooks';
import type { TabType, VideoInfo } from '@/lib/modules/douyin/types';

const PAGE_SIZE = 20;

export default function DouyinPage() {
  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('unread');
  const [page, setPage] = useState(1);

  // Modal 状态
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);

  // 数据获取
  const { videos, loading, refreshing, error, total, refetch: refetchVideos } = useDouyinVideos(
    page,
    PAGE_SIZE,
    activeTab,
  );

  const { pendingCount, refetch: refetchPendingCount } = usePendingCount();

  // 处理完成回调（稳定引用）
  const handleProcessComplete = useCallback(() => {
    setPage(1);
    refetchVideos(true);
    refetchPendingCount();
  }, [refetchVideos, refetchPendingCount]);

  // 处理任务
  const { processing, processMessage, startProcess } = useAsyncProcess(handleProcessComplete);

  // 操作完成回调（稳定引用）
  const handleActionComplete = useCallback(() => {
    setSelectedVideo(null);
    refetchVideos(true);
    refetchPendingCount();
  }, [refetchVideos, refetchPendingCount]);

  // 视频操作
  const { markAsRead, deleteRecord, deleteWithFile } = useVideoActions(handleActionComplete);

  // 打开视频详情
  const handleOpenVideo = useCallback((video: VideoInfo) => {
    setSelectedVideo(video);
  }, []);

  // 关闭弹框
  const handleCloseModal = useCallback(() => {
    setSelectedVideo(null);
  }, []);

  // Tab 切换
  const handleTabChange = useCallback((tabId: string) => {
    setActiveTab(tabId as TabType);
    setPage(1);
  }, []);

  // 标记已读（列表中直接标记）
  const handleMarkAsRead = useCallback(
    async (videoId: string) => {
      try {
        await markAsRead(videoId, true);
      } catch (err) {
        console.error('标记已读失败:', err);
      }
    },
    [markAsRead],
  );

  // 删除记录（列表中直接删除）
  const handleDeleteRecord = useCallback(
    async (videoId: string) => {
      if (!confirm('确定要删除记录吗？（保留原始文件）')) {
        return;
      }
      try {
        await deleteRecord(videoId);
      } catch (err) {
        console.error('删除记录失败:', err);
      }
    },
    [deleteRecord],
  );

  // 删除并取消收藏（列表中直接删除）
  const handleDeleteWithFile = useCallback(
    async (videoId: string) => {
      if (!confirm('确定要删除记录并取消收藏吗？此操作将删除原始文件，无法撤销！')) {
        return;
      }
      try {
        await deleteWithFile(videoId);
      } catch (err) {
        console.error('删除失败:', err);
      }
    },
    [deleteWithFile],
  );

  // Modal 中的操作
  const handleModalMarkAsRead = useCallback(
    async (videoId: string) => {
      try {
        await markAsRead(videoId, true);
      } catch (err) {
        console.error('标记已读失败:', err);
      }
    },
    [markAsRead],
  );

  const handleModalDeleteRecord = useCallback(
    async (videoId: string) => {
      try {
        await deleteRecord(videoId);
      } catch (err) {
        console.error('删除记录失败:', err);
      }
    },
    [deleteRecord],
  );

  const handleModalDeleteWithFile = useCallback(
    async (videoId: string) => {
      try {
        await deleteWithFile(videoId);
      } catch (err) {
        console.error('删除失败:', err);
      }
    },
    [deleteWithFile],
  );

  const tabs = [
    { id: 'unread', label: '未读' },
    { id: 'read', label: '已读' },
  ] as const;

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto p-8">
        {/* 头部导航 */}
        <div className="mb-8">
          <div className="flex justify-between items-start">
            <div>
              <Link href="/" className="text-gray-400 hover:text-white transition-colors">
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4">抖音视频文字稿</h1>
            </div>
            <div className="text-right flex items-center gap-2">
              <button
                onClick={startProcess}
                disabled={processing || loading || refreshing}
                className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
                  pendingCount > 0 ? 'bg-orange-600 hover:bg-orange-700' : 'bg-gray-700 hover:bg-gray-600'
                } disabled:bg-gray-800 disabled:cursor-not-allowed`}
                title={pendingCount > 0 ? `处理 ${pendingCount} 个待处理视频` : '没有待处理的视频'}
              >
                <svg className={`w-5 h-5 ${processing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {processing ? '处理中...' : `待处理 (${pendingCount})`}
              </button>
              <div className="group relative">
                <svg className="w-5 h-5 text-gray-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-gray-800 border border-gray-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10">
                  <p className="text-gray-300 text-sm">点击处理所有待处理的音频文件，后台异步执行 ASR 识别</p>
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
          <Tabs tabs={tabs} activeTab={activeTab} onTabChange={handleTabChange} />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-8 p-4 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-200">错误: {error}</p>
          </div>
        )}

        {/* 加载状态 */}
        {loading && <Loading />}

        {/* 视频列表 */}
        {!loading && videos.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-6 mb-8">
              {videos.map((video) => (
                <VideoCard
                  key={video.aweme_id}
                  video={video}
                  activeTab={activeTab}
                  onClick={() => handleOpenVideo(video)}
                  onMarkAsRead={handleMarkAsRead}
                  onDeleteRecord={handleDeleteRecord}
                  onDeleteWithFile={handleDeleteWithFile}
                />
              ))}
            </div>

            {/* 分页 */}
            {total > PAGE_SIZE && (
              <div className="flex justify-center gap-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  上一页
                </button>
                <span className="px-4 py-2 text-gray-400">
                  第 {page} 页，共 {Math.ceil(total / PAGE_SIZE)} 页
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= Math.ceil(total / PAGE_SIZE)}
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
            <p className="text-gray-400 text-lg">{activeTab === 'unread' ? '暂无未读视频' : '暂无已读视频'}</p>
          </div>
        )}
      </div>

      {/* 视频详情弹框 */}
      {selectedVideo && (
        <VideoModal
          video={selectedVideo}
          onClose={handleCloseModal}
          onMarkAsRead={handleModalMarkAsRead}
          onDeleteRecord={handleModalDeleteRecord}
          onDeleteWithFile={handleModalDeleteWithFile}
        />
      )}
    </main>
  );
}