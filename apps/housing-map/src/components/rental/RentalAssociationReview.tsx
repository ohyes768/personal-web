'use client';

import { useCallback, useEffect, useState } from 'react';
import DirectoryDialog from '../community/DirectoryDialog';
import { rentalDataChanged } from '../../lib/rental-sources';
import { XingfuliProbe } from './XingfuliProbe';

type Candidate = { id: string; name: string; address?: string; district?: string; similarity?: number };
export type RentalReview = { community_id: string; community_name: string; reason: string;
  message?: string; candidates: Candidate[] };
const reasons: Record<string, string> = { needs_selection: '请选择对应小区', missing: '暂无租金来源',
  search_failed: '来源查找失败', search_deferred: '尚未查询，下次更新继续', skipped: '已跳过' };
const filterLabels: Record<string, string> = { needs_selection: '待选择', missing: '未找到',
  search_failed: '查找失败', search_deferred: '未查询', skipped: '已跳过' };
const filterHints: Record<string, string> = {
  needs_selection: '搜索返回了候选，请核对名称、地址与分期后绑定；拿不准可先跳过。',
  missing: '还没有关联租金来源。可以点开小区后用“探查幸福里来源”，只选主页即可，不需要自己找链接。',
  search_failed: '幸福里来源查找或租房入口核验失败，请点开小区查看原因并重试。',
  search_deferred: '匹配任务暂停或等待继续；可在“采集任务”中继续匹配租金来源，也可单独探查。',
  skipped: '之前跳过的小区，可在这里恢复处理。' };
const filterOrder = ['needs_selection', 'missing', 'search_failed', 'search_deferred', 'skipped'];

export function RentalCandidateChoice({ item, busy, onDecide }: {
  item: RentalReview; selected: string; busy: boolean; onSelect: (id: string) => void;
  onDecide: (action: 'bind' | 'skip' | 'reopen') => void;
}) {
  return <div className="directory-candidate">
    <h4>{item.community_name} · {reasons[item.reason] || '待处理'}</h4>
    {item.message && <p className="directory-warning">{item.message}</p>}
    <p className="directory-muted">在下方核对幸福里主页的名称、地址和范围；拿不准可以跳过。</p>

    <div className="directory-actions">
      {item.reason === 'skipped' ? <button className="btn btn-secondary" disabled={busy} onClick={() => onDecide('reopen')}>重新处理</button> : <>
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
      setNotice(action === 'bind' ? '已绑定，请运行“更新租金数据”。' : action === 'skip' ? '已跳过，以后可在“已跳过”中重新处理。' : '已恢复处理，可探查幸福里或运行“匹配租金来源”。');
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
        <XingfuliProbe communityId={item.community_id} onChanged={() => { void load(); onChanged?.(); }} />
      </DirectoryDialog>}</div>
      : <p className="directory-empty">{filterLabels[reasonFilter] || '该类别'}下暂无小区。</p>}
  </section>;
}
