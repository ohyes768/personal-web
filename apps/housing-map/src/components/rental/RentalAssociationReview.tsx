'use client';

import { useCallback, useEffect, useState } from 'react';
import { rentalDataChanged } from '../../lib/rental-sources';

type Candidate = { id: string; name: string; address?: string; district?: string };
export type RentalReview = { community_id: string; community_name: string; reason: string;
  message?: string; candidates: Candidate[] };
const reasons: Record<string, string> = { needs_selection: '请选择对应小区', missing: '暂无租金来源',
  search_failed: '来源查找失败', search_deferred: '尚未查询，下次更新继续', skipped: '已跳过' };

export function RentalCandidateChoice({ item, selected, busy, onSelect, onDecide }: {
  item: RentalReview; selected: string; busy: boolean; onSelect: (id: string) => void;
  onDecide: (action: 'bind' | 'skip' | 'reopen') => void;
}) {
  return <div className="directory-candidate">
    <h4>{item.community_name} · {reasons[item.reason] || '待处理'}</h4>
    {item.message && <p className="directory-warning">{item.message}</p>}
    <p className="directory-muted">核对名称、地址和分期，选一个对应小区；拿不准可以跳过。</p>
    {item.candidates.length ? <fieldset disabled={busy || item.reason === 'skipped'}>
      <legend>房天下候选（单选）</legend>
      {item.candidates.map(candidate => <label key={candidate.id} style={{ display: 'block', margin: '8px 0' }}>
        <input type="radio" name={`rental-${item.community_id}`} checked={selected === candidate.id}
          onChange={() => onSelect(candidate.id)} /> {candidate.name}
        <small style={{ display: 'block', marginLeft: 24 }}>{candidate.address || '地址暂无'} · {candidate.district || '区域待核对'}</small>
      </label>)}
    </fieldset> : <p>暂时没有可选来源，不影响其他小区更新。</p>}
    <div className="directory-actions">
      {item.reason === 'skipped' ? <button className="btn btn-secondary" disabled={busy} onClick={() => onDecide('reopen')}>重新处理</button> : <>
        <button className="btn btn-primary" disabled={busy || !item.candidates.some(c => c.id === selected)} onClick={() => onDecide('bind')}>绑定所选小区</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => onDecide('skip')}>暂时跳过</button>
      </>}
    </div>
  </div>;
}

export default function RentalAssociationReview({ onChanged }: { onChanged?: () => void }) {
  const [items, setItems] = useState<RentalReview[]>([]);
  const [selectedCommunity, setSelectedCommunity] = useState('');
  const [candidate, setCandidate] = useState('');
  const [showSkipped, setShowSkipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch('/api/map/rentals/association-tasks', { signal });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.detail || '租金待处理清单暂不可用');
      if (!signal?.aborted) { setItems(payload.data.items); setError(''); }
    } catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : '清单加载失败'); }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => { if (!controller.signal.aborted) return load(controller.signal); });
    const changed = () => { void load(controller.signal); };
    window.addEventListener('housing-rental-data-changed', changed);
    return () => { controller.abort(); window.removeEventListener('housing-rental-data-changed', changed); };
  }, [load]);
  const visible = items.filter(i => showSkipped ? i.reason === 'skipped' : i.reason !== 'skipped');
  const item = visible.find(i => i.community_id === selectedCommunity);
  async function decide(action: 'bind' | 'skip' | 'reopen') {
    if (!item) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch(`/api/map/rentals/association-tasks/${encodeURIComponent(item.community_id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, ...(action === 'bind' ? { candidate_id: candidate } : {}) }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.detail || '保存失败，请重试');
      setCandidate(''); setSelectedCommunity('');
      setNotice(action === 'bind' ? '已绑定，下次更新租金会采集这个小区。' : action === 'skip' ? '已跳过，以后可在“已跳过”中重新处理。' : '已恢复处理，可选择候选或再次更新租金查找来源。');
      await load(); rentalDataChanged(); onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  }
  return <section aria-label="租金来源待处理" className="directory-collection">
    <h3>租金来源待处理</h3>
    <div className="directory-actions">
      <button className="btn btn-secondary" aria-pressed={!showSkipped} onClick={() => { setShowSkipped(false); setCandidate(''); setSelectedCommunity(''); }}>待处理 {items.filter(i => i.reason !== 'skipped').length}</button>
      <button className="btn btn-secondary" aria-pressed={showSkipped} onClick={() => { setShowSkipped(true); setCandidate(''); setSelectedCommunity(''); }}>已跳过 {items.filter(i => i.reason === 'skipped').length}</button>
      <button className="btn btn-secondary" disabled={busy} onClick={() => void load()}>刷新清单</button>
    </div>
    {error && <p role="alert" className="directory-warning">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {visible.length ? <label>选择待处理小区<select aria-label="待处理租金小区" value={selectedCommunity}
      onChange={e => { setSelectedCommunity(e.target.value); setCandidate(''); }}>
      <option value="">选择小区</option>{visible.map(i => <option key={i.community_id} value={i.community_id}>{i.community_name} · {reasons[i.reason]}</option>)}
    </select></label> : <p className="directory-muted">{showSkipped ? '没有已跳过的小区。' : '目前没有待处理记录；更新租金后会列出需要确认的小区。'}</p>}
    {item && <RentalCandidateChoice item={item} selected={candidate} busy={busy} onSelect={setCandidate} onDecide={action => void decide(action)} />}
  </section>;
}
