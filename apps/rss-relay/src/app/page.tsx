'use client';
import { useState } from 'react';
import { usePosts } from '@/lib/hooks';
import { rssRelayApi } from '@/lib/api';
import type { PostInfo } from '@/lib/types';
import PostCard from '@/components/PostCard';
import PostModal from '@/components/PostModal';
import { RssSubscribe } from '@/components/RssSubscribe';
import { useChannelBrowser } from '@/lib/channel-browser';
import { CopyText } from '@/components/CopyText';
import { feedUrl } from '@/lib/rss-links';

function FilterExtras({ channel, showDisabled, hasDisabled, onToggleDisabled }: { channel: string; showDisabled: boolean; hasDisabled: boolean; onToggleDisabled: (show: boolean) => void }) {
  return <>
    {channel && <CopyText text={feedUrl(channel)} label="订阅" disabled={!process.env.NEXT_PUBLIC_RSS_TOKEN} className="text-xs px-2 py-1 rounded-md border border-accent text-accent hover:bg-accent/10 disabled:opacity-40 whitespace-nowrap" />}
    {hasDisabled && <button onClick={() => onToggleDisabled(!showDisabled)} className="text-xs text-ink-muted underline decoration-dotted underline-offset-2 hover:text-ink whitespace-nowrap" title="已停用渠道仅保留历史内容，可查看不可推送">{showDisabled ? '隐藏停用' : '显示停用'}</button>}
  </>;
}

export default function HomePage() {
  const browser = useChannelBrowser();
  const { posts, loading, error, refresh } = usePosts(50, browser.channel || undefined, browser.ready && (!browser.channel || (browser.loaded && !!browser.active)));
  const [channelSearch, setChannelSearch] = useState('');
  const displayedChannels = browser.channels.filter(c => (browser.showDisabled || c.enabled));
  const searchedChannels = displayedChannels.filter(c => `${c.title} ${c.id}`.toLowerCase().includes(channelSearch.toLowerCase()));
  const refreshAll = () => { void browser.refreshChannels(); void refresh(); };
  const [selected, setSelected] = useState<PostInfo | null>(null);
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
        <div className="max-w-[960px] mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
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
              onClick={refreshAll}
              disabled={loading && !browser.error}
              className="text-[13px] px-3 py-1.5 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors disabled:opacity-50"
              title="刷新"
            >
              {loading ? '加载中…' : '↻ 刷新'}
            </button>
            <RssSubscribe />
            <RssSubscribe manage />
          </div>
        </div>
      </header>

      {/* 内容 */}
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <section aria-label="渠道筛选" className="mb-5 font-ui">
          {browser.error && <p role="alert" className="mb-3 text-sm text-danger">渠道加载失败：{browser.error} <button className="underline" onClick={browser.refreshChannels}>重试</button></p>}
          {!browser.loaded && !browser.error && <p className="text-sm text-ink-muted">加载渠道中…</p>}
          {displayedChannels.length > 8 ? <div className="flex flex-col sm:flex-row gap-2 sm:items-center"><input aria-label="搜索渠道" value={channelSearch} onChange={e => setChannelSearch(e.target.value)} placeholder="搜索渠道名称或标识" className="min-w-0 border border-rule rounded-md bg-paper-card px-2.5 py-1.5 text-[13px]" /><select aria-label="选择查看渠道" value={browser.channel} onChange={e => browser.choose(e.target.value)} className="min-w-0 flex-1 border border-rule rounded-md bg-paper-card px-2.5 py-1.5 text-[13px]"><option value="">全部内容</option>{searchedChannels.map(c => <option key={c.id} value={c.id}>{c.title}{!c.enabled ? '（已停用）' : ''}</option>)}{browser.active && !searchedChannels.some(c => c.id === browser.channel) && <option value={browser.channel}>{browser.active.title}</option>}</select><FilterExtras channel={browser.channel} showDisabled={browser.showDisabled} hasDisabled={browser.channels.some(c => !c.enabled)} onToggleDisabled={browser.toggleDisabled} /></div> : <div className="flex flex-wrap items-center gap-1.5"><button aria-pressed={!browser.channel} onClick={() => browser.choose('')} className={`text-[13px] px-2.5 py-1 rounded-md border ${!browser.channel ? 'border-accent bg-accent/10 text-accent' : 'border-rule text-ink-muted'}`}>全部内容</button>{displayedChannels.map(c => <button key={c.id} aria-pressed={browser.channel === c.id} onClick={() => browser.choose(c.id)} className={`max-w-full break-words text-[13px] px-2.5 py-1 rounded-md border ${browser.channel === c.id ? 'border-accent bg-accent/10 text-accent' : 'border-rule text-ink-muted'}`}>{c.title}{!c.enabled ? ' · 已停用' : ''}</button>)}<FilterExtras channel={browser.channel} showDisabled={browser.showDisabled} hasDisabled={browser.channels.some(c => !c.enabled)} onToggleDisabled={browser.toggleDisabled} /></div>}
          {browser.notice && <p role="status" className="text-sm text-ink-muted mt-3">{browser.notice}</p>}
        </section>
        {error && (
          <div className="mb-4 p-4 bg-danger/[0.06] border border-danger/30 text-danger rounded-[8px] font-ui text-[14px]">
            ⚠️ 加载失败：{error}
          </div>
        )}

        {error || (browser.channel && browser.error) ? null : loading ? (
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
            <p className="font-ui text-[15px]">{browser.active ? '这个渠道还没有内容' : '还没有内容'}</p>
            <p className="font-ui text-[13px] mt-2 text-ink-soft">
              {browser.active?.enabled === false ? '该渠道已停用，暂无保留期内的历史文章。' : '推送内容后会在这里显示；空渠道也可以先订阅。'}
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
                channelTitle={browser.channels.find(c => c.id === (post.channel || 'unclassified'))?.title}
                onChannelSelect={browser.choose}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {selected && (
        <PostModal post={selected} onClose={() => setSelected(null)} />
      )}
    </main>
  );
}
