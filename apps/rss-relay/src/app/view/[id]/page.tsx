'use client';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { rssRelayApi } from '@/lib/api';
import type { PostInfo } from '@/lib/types';
import { formatTime } from '@/lib/hooks';

type DetailStatus = 'loading' | 'ready' | 'notfound' | 'error';

export default function PostDetailPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === 'string' ? params.id : '';
  const [post, setPost] = useState<PostInfo | null>(null);
  const [status, setStatus] = useState<DetailStatus>('loading');

  const load = useCallback(async () => {
    if (!id) return;
    setStatus('loading');
    try {
      const data = await rssRelayApi.getPost(id);
      if (data === null) {
        setStatus('notfound');
      } else {
        setPost(data);
        setStatus('ready');
      }
    } catch {
      setStatus('error');
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="border-b border-rule bg-paper-card/60 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-[920px] mx-auto px-4 sm:px-6 py-4">
          <a
            href="/rss"
            className="font-ui text-[12px] text-ink-muted hover:text-ink-strong transition-colors"
          >
            ← 返回列表
          </a>
        </div>
      </header>

      {/* 内容 */}
      <div className="max-w-[920px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {status === 'loading' && (
          <div className="bg-paper-card border border-rule rounded-[12px] p-5 sm:p-8 animate-pulse">
            <div className="h-6 bg-rule/60 rounded w-3/4 mb-4" />
            <div className="h-3 bg-rule/40 rounded w-1/3 mb-6" />
            <div className="h-3 bg-rule/40 rounded w-full mb-2" />
            <div className="h-3 bg-rule/40 rounded w-full mb-2" />
            <div className="h-3 bg-rule/40 rounded w-2/3" />
          </div>
        )}

        {status === 'notfound' && (
          <div className="text-center py-20 text-ink-soft">
            <div className="text-5xl mb-4">🗂️</div>
            <p className="font-ui text-[15px] text-ink">文章不存在或已过期</p>
            <p className="font-ui text-[13px] mt-2 text-ink-soft">
              内容保留 15 天，链接可能已随保留期失效。
            </p>
            <a
              href="/rss"
              className="inline-block mt-6 font-ui text-[14px] px-4 py-2 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors"
            >
              返回列表
            </a>
          </div>
        )}

        {status === 'error' && (
          <div className="text-center py-20 text-ink-soft">
            <div className="text-5xl mb-4">⚠️</div>
            <p className="font-ui text-[15px] text-danger">加载失败</p>
            <button
              onClick={() => void load()}
              className="mt-6 font-ui text-[14px] px-4 py-2 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors"
            >
              重试
            </button>
          </div>
        )}

        {status === 'ready' && post && (
          <article className="bg-paper-card border border-rule rounded-[12px]">
            {/* 头部：标题 / 来源 / 时间 / 原文链接 */}
            <header className="px-4 sm:px-8 pt-6 pb-4 border-b border-rule">
              <h1 className="font-serif-cn text-[22px] sm:text-[26px] font-bold text-ink-strong leading-tight break-words">
                {post.title}
              </h1>
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
            </header>

            {/* 主体：markdown 渲染 */}
            <div className="px-4 sm:px-8 py-6">
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {post.content}
                </ReactMarkdown>
              </div>
            </div>
          </article>
        )}
      </div>
    </main>
  );
}
