'use client';
import { useEffect, useState } from 'react';
import { rssRelayApi } from '@/lib/api';
import type { Channel } from '@/lib/types';
import { PUBLIC_API, feedUrl, pushExample } from '@/lib/rss-links';
import { unclassifiedLast } from '@/lib/channel-order';
import { RelayDialog } from './RelayDialog';
import { CopyText } from './CopyText';
const button = 'rounded-md bg-paper-deep hover:bg-rule px-3 py-2 text-ink-muted disabled:opacity-40';
const field = 'w-full min-w-0 mt-1 p-2 rounded-md border border-rule bg-paper-deep text-ink';
function ChannelPanel({ onClose, management = false }: { onClose: () => void; management?: boolean }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
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
    setEditing(channel); setError(''); setNotice('');
    setForm(channel === 'new' ? { id: '', title: '', description: '' } : channel);
  };
  const toggle = async (channel: Channel) => {
    setSaving(true); setError('');
    try { await rssRelayApi.updateChannel(channel.id, { enabled: !channel.enabled }); setPendingDisable(null); await load(); setNotice(channel.enabled ? '渠道已停用，原订阅链接仍可读取历史文章。' : '渠道已恢复。'); }
    catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  };
  const visible = unclassifiedLast(channels.filter(c => (management || c.enabled) && `${c.title} ${c.id}`.toLowerCase().includes(search.toLowerCase())));
  return <RelayDialog title={management ? '管理渠道' : '按渠道订阅'} onClose={onClose}>
    <p className="text-ink-muted mb-5 leading-relaxed">{management ? '在这里维护服务名称。渠道标识创建后固定，订阅链接不会因改名改变。' : '复制到 RSS 阅读器，各渠道会单独显示。'}</p>
    {management && <div className="flex gap-2 mb-4"><button className={button} disabled={saving} onClick={() => startEdit('new')}>＋ 新增渠道</button></div>}
    {notice && <p role="status" className="mb-3 p-3 rounded border border-rule bg-paper-deep">{notice}</p>}
    {error && <div role="alert" className="mb-3 text-danger">{error} <button className={button} onClick={load}>重新加载</button></div>}
    {!token && !management && <p className="text-danger mb-3">未配置订阅 token，请联系服务维护者配置后再复制链接。</p>}
    {editing && <form className="border border-rule rounded-lg p-4 mb-5 space-y-3" onSubmit={async e => {
      e.preventDefault(); setSaving(true); setError('');
      try {
        if (editing === 'new') await rssRelayApi.createChannel(form);
        else await rssRelayApi.updateChannel(editing.id, { title: form.title, description: form.description });
        setEditing(null); await load(); setNotice('渠道已保存。');
      } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
      finally { setSaving(false); }
    }}>
      <label className="block">服务名称<input required maxLength={100} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className={field} placeholder="例如：新闻联播服务" /></label>
      <label className="block">渠道标识<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" maxLength={64} disabled={editing !== 'new'} value={form.id} onChange={e => setForm({ ...form, id: e.target.value })} className={`${field} font-mono`} placeholder="例如：xinwen" /><span className="text-xs text-ink-muted">小写字母、数字或连字符，最多 64 位；保存后不可修改。</span></label>
      <label className="block">说明<textarea maxLength={500} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className={field} /></label>
      <div className="flex gap-2"><button disabled={saving} className={button}>{saving ? '保存中…' : '保存渠道'}</button><button type="button" disabled={saving} className={button} onClick={() => setEditing(null)}>取消</button></div>
    </form>}
    {channels.length > 8 && <input aria-label="搜索渠道" placeholder="搜索名称或标识" value={search} onChange={e => setSearch(e.target.value)} className={`${field} mb-4`} />}
    {loading ? <div aria-label="加载渠道中" className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 rounded bg-paper-deep animate-pulse" />)}</div> : <div className="divide-y divide-rule">{visible.map(channel => <div key={channel.id} className="py-4 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><h3 className="font-serif-cn text-lg font-bold break-words">{channel.title}</h3><p className="text-xs text-ink-muted mt-1 break-words">{channel.description || '该渠道的独立订阅'}{management && ` · ${channel.id} · ${channel.enabled ? '启用' : '停用'}`}</p></div>
        {management ? <div className="flex gap-2">{channel.id === 'unclassified' ? <span className="text-xs text-ink-muted py-2">系统渠道</span> : <><button disabled={saving} className={button} onClick={() => startEdit(channel)}>编辑</button><button disabled={saving} className={button} onClick={() => channel.enabled ? setPendingDisable(channel) : void toggle(channel)}>{channel.enabled ? '停用' : '恢复'}</button></>}</div> : <CopyText disabled={!token} text={feedUrl(channel.id)} />}
      </div>
      {!management && <details className="mt-2 text-xs text-ink-muted"><summary className="cursor-pointer py-1">推送示例</summary><p className="font-mono break-all mt-2">POST {PUBLIC_API}/post</p><pre className="overflow-x-auto my-3 p-3 bg-paper-deep rounded text-xs">{pushExample(channel.id)}</pre><CopyText text={pushExample(channel.id)} label="复制推送 JSON" /></details>}
      {pendingDisable?.id === channel.id && <div className="mt-3 p-3 bg-paper-deep rounded"><p>停用「{channel.title}」会暂停接收新推送，保留文章和原订阅链接。</p><div className="flex gap-2 mt-3"><button disabled={saving} className={button} onClick={() => void toggle(channel)}>确认停用</button><button disabled={saving} className={button} onClick={() => setPendingDisable(null)}>取消</button></div></div>}
    </div>)}{!visible.length && <p className="py-4 text-ink-muted">{search ? '没有匹配的渠道。' : '暂无渠道，可以在管理渠道中新增。'}</p>}</div>}
    {!management && <><div className="mt-5 border-t border-rule pt-5"><div className="flex flex-wrap justify-between items-center gap-3"><div><h3 className="font-serif-cn text-lg font-bold">全部内容</h3><p className="text-xs text-ink-muted mt-1">包含所有渠道，与单渠道同时订阅可能重复。</p></div><CopyText disabled={!token} text={feedUrl()} /></div></div><p className="mt-6 text-xs text-ink-muted">订阅链接含 token，请妥善保管。</p></>}
  </RelayDialog>;
}
export function RssSubscribe({ manage = false }: { manage?: boolean }) {
  const [open, setOpen] = useState(false);
  return <><button className="font-ui text-[13px] px-3 py-1.5 rounded-md bg-paper-deep hover:bg-rule text-ink-muted" onClick={() => setOpen(true)}>{manage ? '管理渠道' : '订阅渠道'}</button>{open && <ChannelPanel onClose={() => setOpen(false)} management={manage} />}</>;
}
