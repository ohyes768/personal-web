/**
 * VideoCard 组件
 * Douyin 模块的视频卡片组件
 */
import { VideoInfo, TabType } from '@/lib/types';

export interface VideoCardProps {
  video: VideoInfo;
  activeTab: TabType;
  onClick: () => void;
  onMarkAsRead?: (videoId: string) => void;
  onDeleteRecord?: (videoId: string) => void;
  onDeleteWithFile?: (videoId: string) => void;
}

function getStatusBadge(status: string) {
  switch (status) {
    // v2.0 新状态
    case 'unread':
      return (
        <span className="font-ui px-2 py-0.5 bg-ink-strong/5 text-ink-strong text-[11px] rounded tracking-wider">
          未读
        </span>
      );
    case 'read':
      return (
        <span className="font-ui px-2 py-0.5 bg-success/10 text-success text-[11px] rounded tracking-wider">
          已读
        </span>
      );
    case 'deleted':
      return (
        <span className="font-ui px-2 py-0.5 bg-ink/5 text-ink-soft text-[11px] rounded tracking-wider">
          已删除
        </span>
      );
    // 旧值（迁移前过渡期保留）
    case 'completed':
      return (
        <span className="font-ui px-2 py-0.5 bg-success/10 text-success text-[11px] rounded tracking-wider">
          已识别
        </span>
      );
    case 'processing':
      return (
        <span className="font-ui px-2 py-0.5 bg-accent/10 text-accent text-[11px] rounded tracking-wider">
          识别中
        </span>
      );
    case 'failed':
      return (
        <span className="font-ui px-2 py-0.5 bg-danger/10 text-danger text-[11px] rounded tracking-wider">
          识别失败
        </span>
      );
    case 'pending':
      return (
        <span className="font-ui px-2 py-0.5 bg-ink/5 text-ink-muted text-[11px] rounded tracking-wider">
          待处理
        </span>
      );
    default:
      return null;
  }
}

export function VideoCard({
  video,
  activeTab,
  onClick,
  onMarkAsRead,
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
          {/* 未读 Tab 且状态为 unread/completed 时不显示状态标识（列表默认就是未读） */}
          {(activeTab !== 'unread' || (video.status !== 'unread' && video.status !== 'completed')) && getStatusBadge(video.status)}

          {/* 已读视频（status=read 或 老 is_read=true）显示删除选项 */}
          {activeTab === 'read' && (video.status === 'read' || video.is_read) && (
            <>
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
            </>
          )}

          {/* 未读视频（status=unread 或 老 is_read=false）显示标记已读和删除记录按钮 */}
          {activeTab === 'unread' && video.status !== 'read' && !video.is_read && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onMarkAsRead?.(video.aweme_id);
                }}
                className="font-ui p-1 bg-success/10 hover:bg-success text-success hover:text-paper rounded transition-all opacity-0 group-hover:opacity-100"
                title="标记已读"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </button>
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
            </>
          )}
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