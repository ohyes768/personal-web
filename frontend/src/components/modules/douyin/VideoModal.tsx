/**
 * VideoModal 组件
 * Douyin 模块的视频详情弹框组件
 */
import { useState, useEffect } from 'react';
import { VideoInfo } from '@/lib/modules/douyin/types';
import { useDouyinUtils } from '@/lib/modules/douyin/hooks';
import { Loading } from '@/components/ui/Loading';
import { useVideoDetail } from '@/lib/modules/douyin/hooks';

export interface VideoModalProps {
  video: VideoInfo;
  onClose: () => void;
  onMarkAsRead?: (videoId: string) => void;
  onDeleteRecord?: (videoId: string) => void;
  onDeleteWithFile?: (videoId: string) => void;
}

export function VideoModal({
  video,
  onClose,
  onMarkAsRead,
  onDeleteRecord,
  onDeleteWithFile,
}: VideoModalProps) {
  const { formatTime, formatSegmentTime } = useDouyinUtils();
  const { loading: detailLoading, error: detailError, fetchDetail } = useVideoDetail();

  const [detailVideo, setDetailVideo] = useState<VideoInfo | null>(video);

  // 如果没有详细信息，获取详情
  useEffect(() => {
    if (!video.transcript && video.status === 'completed' && !detailError) {
      fetchDetail(video.aweme_id).then((detail) => {
        if (detail) setDetailVideo(detail);
      });
    }
  }, [video, detailError, fetchDetail]);

  const displayVideo = detailVideo?.transcript ? detailVideo : video;

  const handleMarkAsRead = () => {
    onMarkAsRead?.(displayVideo.aweme_id);
    onClose();
  };

  const handleDeleteRecord = () => {
    onDeleteRecord?.(displayVideo.aweme_id);
    onClose();
  };

  const handleDeleteWithFile = () => {
    onDeleteWithFile?.(displayVideo.aweme_id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
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
            {displayVideo.title || '未知标题'}
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 overflow-y-auto p-6">
          {detailLoading ? (
            <Loading message="加载详情中..." />
          ) : detailError ? (
            <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
              <p className="text-red-200">错误: {detailError}</p>
            </div>
          ) : displayVideo.status === 'failed' ? (
            <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
              <p className="text-red-300">识别失败: {displayVideo.error || '未知错误'}</p>
            </div>
          ) : displayVideo.status === 'pending' || displayVideo.status === 'processing' ? (
            <div className="p-6 bg-blue-900/50 border border-blue-700 rounded-lg">
              <p className="text-blue-200">
                {displayVideo.status === 'processing'
                  ? '视频正在识别中，请稍后再来查看'
                  : '视频尚未处理，请在列表页点击"处理待处理"按钮'}
              </p>
            </div>
          ) : (
            <>
              {/* 视频信息 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 p-4 bg-gray-800/50 rounded-lg">
                <div>
                  <p className="text-gray-400 text-sm mb-1">作者</p>
                  <p className="text-lg">{displayVideo.author || '未知'}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm mb-1">上传时间</p>
                  <p className="text-lg">{formatTime(displayVideo.upload_time)}</p>
                </div>
                {displayVideo.transcript && (
                  <>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">音频时长</p>
                      <p className="text-lg">{displayVideo.transcript.audio_duration.toFixed(2)} 秒</p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">识别置信度</p>
                      <p className="text-lg">{(displayVideo.transcript.confidence * 100).toFixed(1)}%</p>
                    </div>
                  </>
                )}
              </div>

              {/* 描述 */}
              {displayVideo.description && displayVideo.description !== displayVideo.title && (
                <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
                  <p className="text-gray-400 text-sm mb-2">视频描述</p>
                  <p className="text-gray-200">{displayVideo.description}</p>
                </div>
              )}

              {/* 文字稿内容 */}
              {displayVideo.transcript ? (
                <div className="bg-gray-800/50 rounded-lg p-6">
                  <h3 className="text-xl font-bold mb-4">识别文字稿</h3>

                  {displayVideo.transcript.segments && displayVideo.transcript.segments.length > 0 ? (
                    <div className="space-y-3">
                      {displayVideo.transcript.segments.map((segment, index) => (
                        <div key={index} className="flex gap-4 text-lg">
                          <span className="text-gray-500 whitespace-nowrap select-none">
                            [{formatSegmentTime(segment.start_time)} - {formatSegmentTime(segment.end_time)}]
                          </span>
                          <span className="text-gray-300 flex-1 leading-relaxed">{segment.text}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <p className="text-gray-200 leading-loose text-base whitespace-pre-wrap">
                        {displayVideo.transcript.text}
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
            {!displayVideo.is_read && displayVideo.status === 'completed' && (
              <>
                <button
                  onClick={handleMarkAsRead}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition-colors flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  标记已读
                </button>
                <button
                  onClick={handleDeleteRecord}
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
            {displayVideo.is_read && (
              <>
                <button
                  onClick={handleDeleteRecord}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  删除记录
                </button>
                <button
                  onClick={handleDeleteWithFile}
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
          <button onClick={onClose} className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}