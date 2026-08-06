'use client';
import { useState } from 'react';
import { usePosts } from '@/lib/hooks';
import { rssRelayApi } from '@/lib/api';
import type { PostInfo } from '@/lib/types';
import PostCard from '@/components/PostCard';
import PostModal from '@/components/PostModal';
import ApiGuideModal from '@/components/ApiGuideModal';
import { RssSubscribe } from '@/components/RssSubscribe';

export default function HomePage() {
  const { posts, loading, error, refresh } = usePosts(50);
  const [selected, setSelected] = useState<PostInfo | null>(null);
  const [apiOpen, setApiOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (post: PostInfo) => {
    setDeletingId(post.id);
    try {
      await rssRelayApi.deletePost(post.id);
      await refresh(); // 成功后重拉列表，把已删的那条移除
    } catch (e) {
      alert(`删除失败：${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="border-b border-rule bg-paper-card/60 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-[960px] mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <a
              href="/"
              className="font-ui text-[12px] text-ink-muted hover:text-ink-strong transition-colors"
            >
              ← 返回首页
            </a>
            <h1 className="font-serif-cn text-[22px] font-bold text-ink-strong mt-1">
              个人 RSS 中转
            </h1>
            <p className="font-ui text-[12px] text-ink-soft mt-0.5">
              agent 采集推送的 markdown 内容聚合
            </p>
          </div>
          <div className="flex items-center gap-2 font-ui">
            <button
              onClick={refresh}
              disabled={loading}
              className="text-[13px] px-3 py-1.5 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors disabled:opacity-50"
              title="刷新"
            >
              {loading ? '加载中…' : '↻ 刷新'}
            </button>
            <button
              onClick={() => setApiOpen(true)}
              className="text-[13px] px-3 py-1.5 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors"
              title="查看对接文档（怎么接入这个服务）"
            >
              🔌 对接
            </button>
            <RssSubscribe />
          </div>
        </div>
      </header>

      {/* 内容 */}
      <div className="max-w-[960px] mx-auto px-6 py-8">
        {error && (
          <div className="mb-4 p-4 bg-danger/[0.06] border border-danger/30 text-danger rounded-[8px] font-ui text-[14px]">
            ⚠️ 加载失败：{error}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="bg-paper-card border border-rule rounded-[10px] p-5 animate-pulse"
              >
                <div className="h-5 bg-rule/60 rounded w-3/4 mb-3" />
                <div className="h-3 bg-rule/40 rounded w-1/3 mb-3" />
                <div className="h-3 bg-rule/40 rounded w-full" />
              </div>
            ))}
          </div>
        ) : posts.length === 0 ? (
          <div className="text-center py-20 text-ink-soft">
            <div className="text-5xl mb-4">📭</div>
            <p className="font-ui text-[15px]">还没有内容</p>
            <p className="font-ui text-[13px] mt-2 text-ink-soft">
              agent 推送 markdown 后会在这里显示
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                onSelect={setSelected}
                onDelete={handleDelete}
                deleting={deletingId === post.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {selected && (
        <PostModal post={selected} onClose={() => setSelected(null)} />
      )}

      {/* 对接文档 */}
      <ApiGuideModal open={apiOpen} onClose={() => setApiOpen(false)} />
    </main>
  );
}
