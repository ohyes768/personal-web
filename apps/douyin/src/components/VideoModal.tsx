/**
 * VideoModal 组件
 * Douyin 模块的视频详情弹框组件
 */
import { useState, useEffect } from 'react';
import { VideoInfo, TranscriptSegment } from '@/lib/types';
import { useDouyinUtils } from '@/lib/hooks';
import { Loading } from './shared-ui/Loading';
import { useVideoDetail } from '@/lib/hooks';
import { TranscriptToc } from './TranscriptToc';

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
      className="fixed inset-0 z-50 overflow-y-auto bg-ink/45 backdrop-blur-md p-6 sm:p-10"
      onClick={onClose}
    >
      {/* 关闭按钮 */}
      <button
        onClick={onClose}
        className="fixed top-6 right-6 w-10 h-10 border-none bg-paper/90 rounded-full text-ink-muted cursor-pointer text-lg z-[110] shadow-sm hover:bg-paper hover:text-ink hover:scale-105 transition-all"
        aria-label="关闭"
      >
        ✕
      </button>

      {/* 弹框主体：左阅读栏 + 右 TOC */}
      <div
        className="relative max-w-[1100px] mx-auto bg-paper rounded-[14px] shadow-[0_24px_64px_rgba(43,42,40,0.18)] grid grid-cols-1 lg:grid-cols-[1fr_280px] min-h-[calc(100vh-80px)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题 + 正文区 */}
        <div className="px-8 sm:px-14 py-12 sm:py-14 max-w-[calc(68ch+112px)]">
          <h2 className="font-serif-cn text-[28px] sm:text-[32px] font-bold leading-tight text-ink-strong mb-5 tracking-tight">
            {displayVideo.title || '未知标题'}
          </h2>

          <div className="font-ui text-[13px] text-ink-muted pb-7 mb-9 border-b border-rule flex flex-wrap gap-3.5 items-center">
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
                          className="grid grid-cols-[100px_1fr] gap-5 py-[18px] border-b border-dashed border-rule scroll-mt-16 transition-colors hover:bg-accent/[0.03]"
                        >
                          <span className="tnum font-serif-en text-[13px] text-accent font-medium pt-1.5 whitespace-nowrap tracking-wide">
                            {formatSegmentTime(segment.start_time)} — {formatSegmentTime(segment.end_time)}
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

        {/* 右侧 TOC（仅 segments 非空时显示） */}
        {segments.length > 0 && <TranscriptToc segments={segments} />}
      </div>
    </div>
  );
}