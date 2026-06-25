/**
 * VideoModal 组件
 * Douyin 模块的视频详情弹框组件
 */
import { useState, useEffect } from 'react';
import { VideoInfo, TranscriptSegment } from '@/lib/types';
import { useDouyinUtils } from '@/lib/hooks';
import { Loading } from './shared-ui/Loading';
import { useVideoDetail } from '@/lib/hooks';

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

  // 如果没有详细信息，获取详情（兼容 v2.0 status=unread/read 与 旧 completed）
  useEffect(() => {
    const hasTranscript = !!video.transcript;
    const isViewable = video.status === 'unread' || video.status === 'read' || video.status === 'completed';
    if (!hasTranscript && isViewable && !detailError) {
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

  const segments: TranscriptSegment[] = displayVideo.transcript?.segments ?? [];

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md p-4 sm:p-6 flex items-start sm:items-center justify-center"
      onClick={onClose}
    >
      {/* 弹框主体：max-h 限制 + flex column，滚动条在内部 */}
      <div
        className="relative w-full max-w-[920px] max-h-[calc(100vh-32px)] sm:max-h-[calc(100vh-48px)] bg-paper rounded-[14px] shadow-[0_24px_64px_rgba(43,42,40,0.18)] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部：标题 + 关闭按钮（固定不滚） */}
        <header className="shrink-0 relative px-8 sm:px-14 pt-10 sm:pt-12 pb-6 border-b border-rule">
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-9 h-9 border-none bg-paper hover:bg-paper-deep rounded-full text-ink-muted hover:text-ink cursor-pointer text-base flex items-center justify-center transition-all"
            aria-label="关闭"
          >
            ✕
          </button>
          <h2 className="font-serif-cn text-[26px] sm:text-[30px] font-bold leading-tight text-ink-strong tracking-tight pr-12 line-clamp-2">
            {displayVideo.title || '未知标题'}
          </h2>
        </header>

        {/* 主体：滚动区 */}
        <div className="flex-1 overflow-y-auto px-8 sm:px-14 py-8 sm:py-10">
          <div className="font-ui text-[13px] text-ink-muted pb-6 mb-8 border-b border-rule flex flex-wrap gap-3.5 items-center">
            <span>作者 <span className="text-ink-strong font-medium">{displayVideo.author || '未知'}</span></span>
            <span className="text-ink-soft">·</span>
            <span>采集 <span className="text-ink-strong font-medium">{formatTime(displayVideo.upload_time)}</span></span>
            {displayVideo.video_publish_time && (
              <>
                <span className="text-ink-soft">·</span>
                <span>发布 <span className="text-ink-strong font-medium">{formatTime(displayVideo.video_publish_time)}</span></span>
              </>
            )}
            {displayVideo.transcript && (
              <>
                <span className="text-ink-soft">·</span>
                <span>音频 <span className="text-ink-strong font-medium tnum">{displayVideo.transcript.audio_duration.toFixed(0)}秒</span></span>
                <span className="text-ink-soft">·</span>
                <span>置信度 <span className="text-ink-strong font-medium tnum">{(displayVideo.transcript.confidence * 100).toFixed(1)}%</span></span>
              </>
            )}
          </div>

          {detailLoading ? (
            <Loading message="加载详情中..." />
          ) : detailError ? (
            <div className="p-6 bg-danger/10 border border-danger/30 rounded-lg">
              <p className="text-danger">错误: {detailError}</p>
            </div>
          ) : displayVideo.status === 'failed' ? (
            <div className="p-6 bg-danger/10 border border-danger/30 rounded-lg">
              <p className="text-danger">识别失败: {displayVideo.error || '未知错误'}</p>
            </div>
          ) : displayVideo.status === 'pending' || displayVideo.status === 'processing' ? (
            <div className="p-6 bg-ink/5 border border-ink/15 rounded-lg">
              <p className="text-ink-muted">
                {displayVideo.status === 'processing'
                  ? '视频正在识别中，请稍后再来查看'
                  : '视频尚未处理，处理由 douyin-collector 自动推送完成'}
              </p>
            </div>
          ) : displayVideo.status === 'deleted' ? (
            <div className="p-6 bg-ink/5 border border-ink/10 rounded-lg">
              <p className="text-ink-muted">此视频已被删除</p>
            </div>
          ) : (
            <>
              {/* 视频描述 */}
              {displayVideo.description && displayVideo.description !== displayVideo.title && (
                <div className="bg-paper-deep border-l-[3px] border-l-accent px-5 py-4 mb-8 rounded-r-md text-[15px] text-ink-muted leading-relaxed">
                  <div className="font-ui text-[11px] uppercase tracking-[0.15em] text-ink-soft mb-1.5 font-semibold">
                    视频描述
                  </div>
                  {displayVideo.description}
                </div>
              )}

              {/* 文字稿 */}
              {displayVideo.transcript ? (
                <>
                  <div className="font-ui text-[11px] uppercase tracking-[0.2em] text-ink-soft mb-2 font-semibold">
                    识别文字稿
                  </div>
                  <div className="h-px bg-rule mb-6" />

                  {segments.length > 0 ? (
                    <div className="space-y-0">
                      {segments.map((segment, index) => (
                        <div
                          key={index}
                          data-seg-idx={index}
                          className="grid grid-cols-[68px_1fr] gap-3 py-[3px] scroll-mt-16 transition-colors hover:bg-accent/[0.03]"
                        >
                          <span className="tnum font-serif-en text-[11px] text-accent/70 font-normal pt-[7px] whitespace-nowrap tracking-wide select-none">
                            {formatSegmentTime(segment.start_time)}
                          </span>
                          <span className="font-serif-cn text-[18px] leading-[1.85] text-ink tracking-wide">
                            {segment.text}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="font-serif-cn text-[17px] leading-[1.85] text-ink whitespace-pre-wrap tracking-wide">
                      {displayVideo.transcript.text}
                    </p>
                  )}
                </>
              ) : (
                <div className="bg-paper-deep px-6 py-6 rounded-lg">
                  <p className="text-ink-muted">暂无文字稿</p>
                </div>
              )}

              {/* 操作栏 */}
              <div className="mt-10 pt-6 border-t border-rule flex flex-wrap gap-2 justify-between items-center font-ui">
                <div className="flex gap-2 flex-wrap">
                  {(displayVideo.status === 'unread' || (displayVideo.status === 'completed' && !displayVideo.is_read)) && (
                    <>
                      <button
                        onClick={handleMarkAsRead}
                        className="px-4 py-2 rounded-md border border-accent text-accent bg-paper text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 hover:bg-accent hover:text-paper"
                      >
                        <span>✓</span>
                        标记已读
                      </button>
                      <button
                        onClick={handleDeleteRecord}
                        className="px-4 py-2 rounded-md border border-rule text-ink bg-paper text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 hover:border-ink-soft hover:bg-paper-deep"
                      >
                        删除记录
                      </button>
                    </>
                  )}
                  {(displayVideo.status === 'read' || displayVideo.is_read) && (
                    <>
                      <button
                        onClick={handleDeleteRecord}
                        className="px-4 py-2 rounded-md border border-rule text-ink bg-paper text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 hover:border-ink-soft hover:bg-paper-deep"
                      >
                        删除记录
                      </button>
                      <button
                        onClick={handleDeleteWithFile}
                        className="px-4 py-2 rounded-md border border-danger text-danger bg-paper text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 hover:bg-danger hover:text-paper"
                      >
                        删除并取消收藏
                      </button>
                    </>
                  )}
                </div>
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-md border border-rule text-ink-muted bg-paper text-[13px] cursor-pointer transition-all hover:border-ink-soft hover:text-ink"
                >
                  关闭
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}