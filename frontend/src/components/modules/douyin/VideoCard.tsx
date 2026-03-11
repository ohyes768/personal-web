/**
 * VideoCard 组件
 * Douyin 模块的视频卡片组件
 */
import { VideoInfo, TabType } from '@/lib/modules/douyin/types';

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
    case 'completed':
      return (
        <span className="px-3 py-1 bg-green-900/50 text-green-300 text-sm rounded-full whitespace-nowrap">
          已识别
        </span>
      );
    case 'processing':
      return (
        <span className="px-3 py-1 bg-yellow-900/50 text-yellow-300 text-sm rounded-full whitespace-nowrap">
          识别中
        </span>
      );
    case 'failed':
      return (
        <span className="px-3 py-1 bg-red-900/50 text-red-300 text-sm rounded-full whitespace-nowrap">
          识别失败
        </span>
      );
    case 'pending':
      return (
        <span className="px-3 py-1 bg-gray-700/50 text-gray-300 text-sm rounded-full whitespace-nowrap">
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
      className="relative group p-6 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors border border-gray-800 cursor-pointer"
    >
      <div className="flex justify-between items-start mb-3">
        <h3 className="text-xl font-bold flex-1 pr-4">{video.title || '未知标题'}</h3>
        <div className="flex items-center gap-2">
          {/* 未读 Tab 且状态为 completed 时不显示状态标识 */}
          {(activeTab !== 'unread' || video.status !== 'completed') && getStatusBadge(video.status)}

          {/* 已读视频显示删除选项 */}
          {activeTab === 'read' && video.is_read && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteRecord?.(video.aweme_id);
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
                  onDeleteWithFile?.(video.aweme_id);
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

          {/* 未读视频显示标记已读和删除记录按钮 */}
          {activeTab === 'unread' && !video.is_read && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onMarkAsRead?.(video.aweme_id);
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
                  onDeleteRecord?.(video.aweme_id);
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

      <p className="text-gray-400 mb-2">作者: {video.author || '未知'}</p>

      <p className="text-gray-600 text-sm">
        {video.upload_time ? new Date(video.upload_time).toLocaleString() : '未知时间'}
      </p>
    </div>
  );
}