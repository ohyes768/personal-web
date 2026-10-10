'use client';
import { useEffect, useState } from 'react';
import { rssRelayApi } from '@/lib/api';
import type { Channel } from '@/lib/types';
import { PUBLIC_API, feedUrl, pushExample } from '@/lib/rss-links';
import { unclassifiedLast } from '@/lib/channel-order';
import { RelayDialog } from './RelayDialog';
import { CopyText } from './CopyText';
const button = 'rounded-md bg-paper-deep hover:bg-rule px-2.5 py-1.5 text-xs text-ink-muted disabled:opacity-40 whitespace-nowrap';
const copyButton = 'rounded-md border border-accent px-2.5 py-1.5 text-xs text-accent hover:bg-accent/10 disabled:opacity-40 whitespace-nowrap';
const field = 'w-full min-w-0 mt-1 p-2 rounded-md border border-rule bg-paper-deep text-ink';
function ChannelPanel({ onClose, onChannelsChange }: { onClose: () => void; onChannelsChange: () => void }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [showDisabled, setShowDisabled] = useState(false);
  const [actions, setActions] = useState<string | null>(null);
  const [example, setExample] = useState<string | null>(null);
  const [editing, setEditing] = useState<Channel | 'new' | null>(null);
  const [form, setForm] = useState({ id: '', title: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [pendingDisable, setPendingDisable] = useState<Channel | null>(null);
  const token = process.env.NEXT_PUBLIC_RSS_TOKEN || '';
  const load = async () => {
    setLoading(true); setError('');
    try { setChannels((await rssRelayApi.getChannels(true)).channels); }
    catch (e) { setError(e instanceof Error ? e.message : '加载失败'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const startEdit = (channel: Channel | 'new') => {
    setEditing(channel); setActions(null); setPendingDisable(null); setError(''); setNotice('');
    setForm(channel === 'new' ? { id: '', title: '', description: '' } : channel);
    if (channel === 'new') setSearch('');
  };
  const applyChannel = (updated: Channel) => {
    setChannels(current => current.some(c => c.id === updated.id) ? current.map(c => c.id === updated.id ? updated : c) : [...current, updated]);
    onChannelsChange();
  };
  const toggle = async (channel: Channel) => {
    setSaving(true); setError('');
    try { applyChannel(await rssRelayApi.updateChannel(channel.id, { enabled: !channel.enabled })); setPendingDisable(null); setActions(null); setNotice(channel.enabled ? '渠道已停用，原订阅链接仍可读取历史文章。' : '渠道已恢复。'); }
    catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  };
  const visible = unclassifiedLast(channels.filter(c => (showDisabled || c.enabled) && `${c.title} ${c.id}`.toLowerCase().includes(search.trim().toLowerCase())));
  const editForm = editing && <form className="border border-rule rounded-lg p-3 my-2 space-y-2" onSubmit={async e => {
      e.preventDefault(); setSaving(true); setError('');
      try {
        const updated = editing === 'new' ? await rssRelayApi.createChannel(form) : await rssRelayApi.updateChannel(editing.id, { title: form.title, description: form.description });
        applyChannel(updated); setEditing(null); setNotice('渠道已保存。');
      } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
      finally { setSaving(false); }
    }}>
      <label className="block">服务名称<input autoFocus required maxLength={100} disabled={saving} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className={field} placeholder="例如：新闻联播服务" /></label>
      <label className="block">渠道标识<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" maxLength={64} disabled={saving || editing !== 'new'} value={form.id} onChange={e => setForm({ ...form, id: e.target.value })} className={`${field} font-mono`} placeholder="例如：xinwen" /><span className="text-xs text-ink-muted">小写字母、数字或连字符，最多 64 位；保存后不可修改。</span></label>
      <label className="block">说明<textarea rows={2} maxLength={500} disabled={saving} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className={field} /></label>
      <div className="flex gap-2"><button disabled={saving} className={button}>{saving ? '保存中…' : '保存渠道'}</button><button type="button" disabled={saving} className={button} onClick={() => setEditing(null)}>取消</button></div>
    </form>;
  return <RelayDialog title="渠道" onClose={onClose}>
    <div className="flex gap-2 mb-3"><input aria-label="搜索渠道" placeholder="搜索名称或标识" value={search} disabled={!!editing} onChange={e => setSearch(e.target.value)} className="min-w-0 flex-1 px-2.5 py-1.5 rounded-md border border-rule bg-paper-deep text-xs" /><button className={button} disabled={loading || saving || !!editing} onClick={() => startEdit('new')}>＋ 新增</button></div>
    <div className="flex items-center justify-between gap-2 mb-2 text-xs text-ink-muted"><span>复制链接到 RSS 阅读器</span><label className="flex items-center gap-1.5 whitespace-nowrap"><input type="checkbox" checked={showDisabled} disabled={!!editing || saving} onChange={e => { setShowDisabled(e.target.checked); setActions(null); setPendingDisable(null); }} />显示已停用</label></div>
    {notice && <p role="status" className="mb-3 p-3 rounded border border-rule bg-paper-deep">{notice}</p>}
    {error && <div role="alert" className="mb-3 text-danger">{error} <button className={button} onClick={load}>重新加载</button></div>}
    {!token && <p className="text-danger mb-2 text-xs">未配置订阅 token，请联系服务维护者配置后再复制链接。</p>}
    {editing === 'new' && editForm}
    <div className="flex items-center justify-between gap-2 border-b border-rule py-2.5 mb-1"><div className="min-w-0"><h3 className="font-serif-cn font-bold">全部内容</h3><p className="text-xs text-ink-muted mt-0.5">与单渠道同时订阅可能重复</p></div><div className="shrink-0"><CopyText disabled={!token} text={feedUrl()} className={copyButton} /></div></div>
    {loading ? <div aria-label="加载渠道中" className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-14 rounded bg-paper-deep animate-pulse" />)}</div> : <div className="divide-y divide-rule">{visible.map(channel => <div key={channel.id} data-channel-row={channel.id} className="py-2.5">
      <div className="flex items-center gap-2"><h3 title={channel.title} className="min-w-0 flex-1 truncate font-serif-cn font-bold">{channel.title}</h3>
        {!channel.enabled && <span className="shrink-0 text-[11px] text-ink-muted">已停用</span>}
        <div className="shrink-0"><CopyText disabled={!token} text={feedUrl(channel.id)} className={copyButton} /></div>
        {channel.id !== 'unclassified' && <button aria-label={`管理${channel.title}`} aria-expanded={actions === channel.id} aria-controls={`channel-actions-${channel.id}`} disabled={saving || !!editing} className={`${button} w-8 px-0`} onClick={() => { setActions(actions === channel.id ? null : channel.id); setPendingDisable(null); }}>⋯</button>}
      </div>
      <div className="flex items-center gap-2 mt-0.5 text-xs text-ink-muted"><p title={channel.description || channel.id} className="min-w-0 flex-1 truncate">{channel.description || channel.id}{channel.id === 'unclassified' ? ' · 系统渠道' : ''}</p><button aria-expanded={example === channel.id} aria-controls={`channel-example-${channel.id}`} className="shrink-0 text-[11px] hover:text-ink py-0.5" onClick={() => setExample(example === channel.id ? null : channel.id)}>{example === channel.id ? '▾' : '▸'} 推送示例</button></div>
      {actions === channel.id && <div id={`channel-actions-${channel.id}`} className="flex items-center gap-2 mt-2 p-2 rounded bg-paper-deep"><span title={channel.id} className="min-w-0 flex-1 truncate font-mono text-xs text-ink-muted">{channel.id}</span><button disabled={saving} className={button} onClick={() => startEdit(channel)}>编辑</button><button disabled={saving} className={button} onClick={() => channel.enabled ? setPendingDisable(channel) : void toggle(channel)}>{channel.enabled ? '停用' : '恢复'}</button></div>}
      {editing && editing !== 'new' && editing.id === channel.id && editForm}
      {example === channel.id && <div id={`channel-example-${channel.id}`} className="mt-2 text-xs text-ink-muted"><p className="font-mono break-all">POST {PUBLIC_API}/post</p><pre className="overflow-x-auto my-2 p-2 bg-paper-deep rounded text-xs">{pushExample(channel.id)}</pre><CopyText text={pushExample(channel.id)} label="复制推送 JSON" className={button} /></div>}
      {pendingDisable?.id === channel.id && <div className="mt-3 p-3 bg-paper-deep rounded"><p>停用「{channel.title}」会暂停接收新推送，保留文章和原订阅链接。</p><div className="flex gap-2 mt-3"><button disabled={saving} className={button} onClick={() => void toggle(channel)}>确认停用</button><button disabled={saving} className={button} onClick={() => setPendingDisable(null)}>取消</button></div></div>}
    </div>)}{!visible.length && <p className="py-3 text-xs text-ink-muted">{search ? '没有匹配的渠道。' : '暂无启用渠道，可新增或显示已停用渠道。'}</p>}</div>}
    <p className="mt-3 text-[11px] text-ink-muted">订阅链接含 token，请妥善保管。改名不改变订阅链接。</p>
  </RelayDialog>;
}
export function RssSubscribe({ onChannelsChange }: { onChannelsChange: () => void }) {
  const [open, setOpen] = useState(false);
  return <><button className="font-ui text-[13px] px-3 py-1.5 rounded-md bg-paper-deep hover:bg-rule text-ink-muted" onClick={() => setOpen(true)}>渠道</button>{open && <ChannelPanel onClose={() => setOpen(false)} onChannelsChange={onChannelsChange} />}</>;
}
