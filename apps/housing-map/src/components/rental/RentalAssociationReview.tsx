'use client';

import { useCallback, useEffect, useState } from 'react';
import DirectoryDialog from '../community/DirectoryDialog';
import { rentalDataChanged } from '../../lib/rental-sources';

type Candidate = { id: string; name: string; address?: string; district?: string; similarity?: number };
export type RentalReview = { community_id: string; community_name: string; reason: string;
  message?: string; candidates: Candidate[] };
const reasons: Record<string, string> = { needs_selection: '请选择对应小区', missing: '暂无租金来源',
  search_failed: '来源查找失败', search_deferred: '尚未查询，下次更新继续', skipped: '已跳过' };
const pct = (value?: number) => value == null ? '' : ` · 相似度 ${Math.round(value * 100)}%`;
const filterLabels: Record<string, string> = { needs_selection: '待选择', missing: '未找到',
  search_failed: '查找失败', search_deferred: '未查询', skipped: '已跳过' };
const filterHints: Record<string, string> = {
  needs_selection: '搜索返回了候选，请核对名称、地址与分期后绑定；拿不准可先跳过。',
  missing: '房天下没搜到像样的候选；等下轮更新重试，或在小区详情“租金与收益”里粘贴房天下小区租房页链接。',
  search_failed: '上一轮查找失败（常见为房天下临时拦截），稍后重新采集租金即可。',
  search_deferred: '本轮尚未查询，之后的更新会自动继续，无需操作。',
  skipped: '之前跳过的小区，可在这里恢复处理。' };
const filterOrder = ['needs_selection', 'missing', 'search_failed', 'search_deferred', 'skipped'];

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
          onChange={() => onSelect(candidate.id)} /> {candidate.name}{pct(candidate.similarity)}
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
  const [reasonFilter, setReasonFilter] = useState('needs_selection');
  const [selectedCommunity, setSelectedCommunity] = useState('');
  const [candidate, setCandidate] = useState('');
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
  const counts: Record<string, number> = {};
  for (const entry of items) counts[entry.reason] = (counts[entry.reason] || 0) + 1;
  const visible = items.filter(i => i.reason === reasonFilter);
  const item = visible.find(i => i.community_id === selectedCommunity);
  function pickFilter(reason: string) { setReasonFilter(reason); setSelectedCommunity(''); setCandidate(''); }
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
      setSelectedCommunity('');
      setCandidate('');
      setNotice(action === 'bind' ? '已绑定，下次更新租金会采集这个小区。' : action === 'skip' ? '已跳过，以后可在“已跳过”中重新处理。' : '已恢复处理，可选择候选或再次更新租金查找来源。');
      await load(); rentalDataChanged(); onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  }
  return <section aria-label="租金来源待处理" className="directory-collection">
    <h3>租金来源待处理</h3>
    <div className="directory-actions">
      {filterOrder.map(reason => <button key={reason} className="btn btn-secondary" aria-pressed={reasonFilter === reason}
        onClick={() => pickFilter(reason)}>{filterLabels[reason]} {counts[reason] || 0}</button>)}
      <button className="btn btn-secondary" disabled={busy} onClick={() => void load()}>刷新清单</button>
    </div>
    {error && !item && <p role="alert" className="directory-warning">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <p className="directory-muted">{filterHints[reasonFilter] || ''}</p>
    {visible.length ? <div className="directory-workspace"><div className="directory-list-panel">
      <div className="rental-source-list">{visible.map(entry => {
        const top = Math.max(0, ...entry.candidates.map(c => c.similarity ?? 0));
        return <button key={entry.community_id} type="button"
          aria-pressed={selectedCommunity === entry.community_id}
          onClick={() => { setSelectedCommunity(entry.community_id === selectedCommunity ? '' : entry.community_id); setCandidate(''); }}>
          <span>{entry.community_name}</span><small>{filterLabels[entry.reason] || entry.reason}{top > 0 ? ` · ${Math.round(top * 100)}%` : ''}</small></button>;
      })}</div>
    </div>
      {item && <DirectoryDialog title={item.community_name} onClose={() => { setSelectedCommunity(''); setCandidate(''); }}>
        {error && <p role="alert" className="directory-warning">{error}</p>}
        <RentalCandidateChoice item={item} selected={candidate} busy={busy} onSelect={setCandidate} onDecide={action => void decide(action)} />
      </DirectoryDialog>}</div>
      : <p className="directory-empty">{filterLabels[reasonFilter] || '该类别'}下暂无小区。</p>}
  </section>;
}
