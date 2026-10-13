'use client';

import { useEffect, useState } from 'react';
import { fetchAuctionData } from '../../lib/auction-types';
import { SafeLink, statuses } from '../community/CommunityAuctionHistory';
import styles from './AuctionPendingAssociations.module.css';

type Candidate = { community_id: string; community_name: string; address?: string; evidence?: string[] };
type Pending = { record_id: string; name: string; address?: string; reason: string;
  source_kind: string; source_id: string; candidates: Candidate[];
  rounds: { auction_id: string; title: string; status: string; round?: number; source_url?: string }[] };
type PendingPage = { items: Pending[]; total: number; needs_sync: boolean };

function BindingForm({ item, onChanged }: { item: Pending; onChanged: () => void }) {
  const [query, setQuery] = useState('');
  const [targets, setTargets] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!query.trim()) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchAuctionData<{ items: Candidate[] }>(`directory/communities?q=${encodeURIComponent(query)}&district=滨江&page_size=100`, controller.signal)
        .then(data => { if (!controller.signal.aborted) setTargets(data.items); })
        .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query]);
  async function bind() {
    if (!selected) return;
    setBusy(true); setError('');
    try {
      await fetchAuctionData(`directory/sources/${encodeURIComponent(item.record_id)}/associate`, undefined,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ community_id: selected.community_id }) });
      onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '关联失败，请重试'); }
    finally { setBusy(false); }
  }
  const choices = query.trim() ? targets : item.candidates;
  return <div>
    <p>{item.reason}</p>
    <label className={styles.search}>搜索目标小区<input aria-label={`为${item.name}搜索目标小区`} placeholder="输入小区名称或别名" value={query}
      maxLength={100} onChange={e => { setQuery(e.target.value); setTargets([]); setSelected(null); setConfirming(false); setError(''); }} /></label>
    <div className={`directory-candidate ${styles.choices}`}>
      {choices.map(c => <div key={c.community_id}><label><input type="radio" name={`target-${item.record_id}`} checked={selected?.community_id === c.community_id}
        onChange={() => { setSelected(c); setConfirming(false); }} />{c.community_name} · {c.address || '地址未知'}</label>
        {c.evidence?.map((text, i) => <p className="auction-meta" key={i}>{text}</p>)}</div>)}
      {!choices.length && <p>暂无候选，可搜索已有小区。目录里没有的小区，请先到小区数据管理补齐。</p>}
    </div>
    {confirming && selected && <p>确认这处房产属于“{selected.community_name}”？请核对地址与分期。{item.source_kind === 'asset' ? '绑定将用于这处房产的所有拍卖轮次。' : '缺少房产编号，本次仅绑定这一拍卖记录。'}</p>}
    <div className="directory-actions"><button className="btn btn-primary" disabled={busy || !selected} onClick={() => confirming ? void bind() : setConfirming(true)}>
      {busy ? '正在保存…' : confirming ? '确认绑定' : '关联所选小区'}</button>
      {confirming && <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming(false)}>取消</button>}</div>
    {error && <p role="alert">{error}</p>}
  </div>;
}

export default function AuctionPendingAssociations({ refreshVersion, onChanged }: { refreshVersion: number; onChanged: () => void }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ key: string; data?: PendingPage; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const key = JSON.stringify([page, refreshVersion, revision]);
  useEffect(() => {
    const controller = new AbortController();
    fetchAuctionData<PendingPage>(`auctions/associations/pending?page=${page}`, controller.signal)
      .then(data => { if (!controller.signal.aborted) {
        if (page > 1 && !data.items.length) { setPage(Math.max(1, Math.ceil(data.total / 20))); return; }
        setState({ key, data });
      } })
      .catch(e => { if (!controller.signal.aborted) setState({ key, error: e.message }); });
    return () => controller.abort();
  }, [page, refreshVersion, revision, key]);
  async function sync() {
    setBusy(true); setNotice('');
    try {
      const data = await fetchAuctionData<{ identities: number; matched: number; pending: number; ignored: number }>('auctions/associations/sync', undefined, { method: 'POST' });
      setNotice(`已同步 ${data.identities} 处房产：已关联 ${data.matched}，待关联 ${data.pending}，已跳过 ${data.ignored}。`);
      setRevision(v => v + 1); onChanged();
    } catch (e) { setNotice(e instanceof Error ? e.message : '同步失败，请重试'); }
    finally { setBusy(false); }
  }
  function changed() { setNotice('绑定已保存，法拍列表和小区统计已更新。'); setRevision(v => v + 1); onChanged(); }
  const current = state?.key === key ? state : null;
  return <section aria-label="法拍手工待关联" className={`auction-list-card ${styles.panel}`}>
    <div className="directory-actions"><h3>手工待关联</h3><button className="btn btn-secondary" disabled={busy} onClick={() => void sync()}>{busy ? '正在同步…' : '同步历史记录 / 重试关联同步'}</button></div>
    <p className="auction-meta">按房产归组，同一房产多次拍卖只需绑定一次。同步使用已保存的法拍记录，不重新采集。</p>
    {notice && <p role="status">{notice}</p>}
    {!current && <p role="status">正在加载待关联房产…</p>}
    {current?.error && <p role="alert">{current.error} <button className="btn btn-secondary" onClick={() => setRevision(v => v + 1)}>重试</button></p>}
    {current?.data && <>
      {current.data.needs_sync && <p role="status">有历史记录尚未进入关联目录，请点击“同步历史记录”。</p>}
      <p>待关联 {current.data.total} 处房产</p>
      {!current.data.items.length && <p>{current.data.needs_sync ? '同步后可查看待关联房产。' : '没有待关联房产。'}</p>}
      {current.data.items.map(item => <details className="auction-list-card" key={item.record_id}><summary>{item.name} · {item.rounds.length} 条拍卖记录</summary>
        <p>{item.address || '地址未知'}</p><p className="auction-meta">{item.source_kind === 'asset' ? '房产编号' : '拍卖编号'} {item.source_id}</p>
        {item.rounds.map(r => <p key={r.auction_id}>{r.title} · {statuses[r.status] || '状态未知'} <SafeLink url={r.source_url}>查看来源</SafeLink></p>)}
        <BindingForm item={item} onChanged={changed} />
      </details>)}
      {current.data.total > 20 && <nav className="auction-pagination" aria-label="待关联分页"><button disabled={page === 1} onClick={() => setPage(v => v - 1)}>上一页</button><span>{page} / {Math.ceil(current.data.total / 20)}</span><button disabled={page * 20 >= current.data.total} onClick={() => setPage(v => v + 1)}>下一页</button></nav>}
    </>}
  </section>;
}
