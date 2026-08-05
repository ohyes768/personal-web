/**
 * VideoCard 组件
 * Douyin 模块的视频卡片组件
 */
import { VideoInfo } from '@/lib/types';

export interface VideoCardProps {
  video: VideoInfo;
  onClick: () => void;
  onDeleteRecord?: (videoId: string) => void;
  onDeleteWithFile?: (videoId: string) => void;
}

export function VideoCard({
  video,
  onClick,
  onDeleteRecord,
  onDeleteWithFile,
}: VideoCardProps) {
  return (
    <div
      onClick={onClick}
      className="group relative p-6 sm:p-7 bg-paper-card border border-rule rounded-[10px] cursor-pointer transition-all duration-200 shadow-[0_1px_2px_rgba(43,42,40,0.04),0_2px_8px_rgba(43,42,40,0.04)] hover:-translate-y-px hover:shadow-[0_4px_12px_rgba(43,42,40,0.06),0_16px_32px_rgba(43,42,40,0.06)] hover:border-ink-soft"
    >
      <div className="flex justify-between items-start mb-2.5 gap-4">
        <h3 className="font-serif-cn text-[19px] sm:text-[20px] font-bold flex-1 text-ink-strong leading-snug tracking-tight">
          {video.title || '未知标题'}
        </h3>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDeleteRecord?.(video.aweme_id);
            }}
            className="font-ui p-1 bg-ink/5 hover:bg-ink/15 text-ink-muted rounded transition-all opacity-0 group-hover:opacity-100"
            title="删除记录"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDeleteWithFile?.(video.aweme_id);
            }}
            className="font-ui p-1 bg-danger/10 hover:bg-danger text-danger hover:text-paper rounded transition-all opacity-0 group-hover:opacity-100"
            title="删除并取消收藏"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>

      <p className="font-ui text-[13px] text-ink-muted mb-3.5 flex items-center gap-2.5">
        <span>{video.author || '未知'}</span>
        <span className="text-ink-soft">·</span>
        <span>
          {video.upload_time
            ? `采集于 ${new Date(video.upload_time).toLocaleString('zh-CN')}`
            : '采集时间未知'}
        </span>
      </p>

      {/* 文字稿预览 */}
      <div>
        {video.transcript?.text ? (
          <p className="text-ink-muted text-[15px] leading-[1.7] line-clamp-2 m-0">
            {video.transcript.text.slice(0, 120)}
            {video.transcript.text.length > 120 ? '...' : ''}
          </p>
        ) : (
          <p className="text-ink-soft text-[14px] italic">无解说</p>
        )}
      </div>
    </div>
  );
}