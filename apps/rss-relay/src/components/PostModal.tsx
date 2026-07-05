'use client';
import { useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { PostInfo } from '@/lib/types';
import { formatTime } from '@/lib/hooks';

interface Props {
  post: PostInfo;
  onClose: () => void;
}

export default function PostModal({ post, onClose }: Props) {
  // Esc 关闭 + 锁滚动
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-paper-card rounded-[12px] w-full max-w-[920px] my-4 shadow-[0_8px_32px_rgba(43,42,40,0.15)] flex flex-col max-h-[calc(100vh-4rem)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <header className="px-6 sm:px-8 pt-6 pb-4 border-b border-rule">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="font-serif-cn text-[22px] sm:text-[26px] font-bold text-ink-strong leading-tight">
                {post.title}
              </h2>
              <div className="mt-2 flex flex-wrap items-center gap-3 font-ui text-[13px] text-ink-muted">
                {post.source && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-[4px] bg-accent/[0.08] text-accent font-medium">
                    {post.source}
                  </span>
                )}
                <time className="tnum">{formatTime(post.created_at)}</time>
                {post.url && (
                  <a
                    href={post.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    原文链接 ↗
                  </a>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full hover:bg-paper-deep transition-colors text-ink-muted hover:text-ink"
              aria-label="关闭"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </header>

        {/* 主体：markdown 渲染 */}
        <div className="flex-1 overflow-y-auto px-6 sm:px-8 py-6">
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {post.content}
            </ReactMarkdown>
          </div>
        </div>

        {/* 底部 */}
        <footer className="px-6 sm:px-8 py-4 border-t border-rule flex justify-end">
          <button
            onClick={onClose}
            className="font-ui text-[14px] px-4 py-2 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors"
          >
            关闭
          </button>
        </footer>
      </div>
    </div>
  );
}
