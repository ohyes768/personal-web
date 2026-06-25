'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { Tabs } from '@/components/shared-ui/Tabs';
import { Loading } from '@/components/shared-ui/Loading';
import { VideoCard } from '@/components/VideoCard';
import { VideoModal } from '@/components/VideoModal';
import { useDouyinVideos, usePendingCount, useAsyncProcess, useVideoActions } from '@/lib/hooks';
import type { TabType, VideoInfo } from '@/lib/types';

export default function DouyinPage() {
  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('unread');

  // Modal 状态
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);

  // 数据获取
  const { videos, loading, refreshing, error, refetch: refetchVideos } = useDouyinVideos(
    activeTab,
  );

  const { pendingCount, refetch: refetchPendingCount } = usePendingCount();

  // 处理完成回调（稳定引用）
  const handleProcessComplete = useCallback(() => {
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
    { id: 'unread', label: '未读', badge: pendingCount || undefined },
    { id: 'read', label: '已读' },
  ] as const;

  return (
    <main className="min-h-screen bg-paper text-ink">
      <div className="max-w-[960px] mx-auto px-6 sm:px-8 py-10 sm:py-12 pb-20">
        {/* 头部导航 */}
        <header className="flex flex-wrap justify-between items-center gap-5 mb-12 pb-6 border-b border-rule">
          <Link
            href="/"
            className="font-ui text-ink-muted hover:text-ink text-[14px] transition-colors no-underline whitespace-nowrap"
          >
            ← 返回首页
          </Link>
          <h1 className="font-serif-cn font-bold text-[22px] text-ink-strong flex-1 text-center order-first sm:order-none basis-full sm:basis-auto tracking-wide">
            抖音视频文字稿
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={startProcess}
              disabled={processing || loading || refreshing}
              className={`font-ui px-3.5 py-2 rounded-md text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed ${
                pendingCount > 0
                  ? 'border border-accent text-accent bg-accent/[0.04] hover:bg-accent hover:text-paper'
                  : 'border border-rule text-ink bg-paper hover:border-ink-soft'
              }`}
              title={pendingCount > 0 ? `处理 ${pendingCount} 个待处理视频` : '没有待处理的视频'}
            >
              <svg
                className={`w-4 h-4 ${processing ? 'animate-spin' : ''}`}
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
              {processing ? '处理中...' : `待处理 (${pendingCount})`}
            </button>
            <div className="group relative">
              <svg
                className="w-4 h-4 text-ink-muted cursor-help"
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
              <div className="font-ui absolute right-0 top-full mt-2 w-64 p-3 bg-ink-strong text-paper text-[13px] rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10 leading-relaxed">
                点击启动 ASR 处理 pending 视频（后台串行运行，慢慢来）
              </div>
            </div>
          </div>
        </header>

        {/* 处理状态提示 */}
        {processMessage && (
          <div className="font-ui mb-6 p-4 bg-paper-deep border-l-[3px] border-l-accent rounded-r-md text-ink-muted text-[14px]">
            {processMessage}
          </div>
        )}

        {/* Tab 切换 */}
        <div className="mb-8">
          <Tabs tabs={tabs} activeTab={activeTab} onTabChange={handleTabChange} />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="font-ui mb-8 p-4 bg-danger/10 border border-danger/30 rounded-lg text-danger text-[14px]">
            错误: {error}
          </div>
        )}

        {/* 加载状态 */}
        {loading && <Loading />}

        {/* 视频列表 */}
        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-1 gap-4 mb-8">
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
        )}

        {/* 空状态 */}
        {!loading && videos.length === 0 && !error && (
          <div className="text-center py-16 font-ui">
            <p className="text-ink-soft text-[15px]">
              {activeTab === 'unread' ? '暂无未读视频' : '暂无已读视频'}
            </p>
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