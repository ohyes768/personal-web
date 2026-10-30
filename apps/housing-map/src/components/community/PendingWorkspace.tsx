'use client';

import { useEffect, useRef, useState } from 'react';
import type { Auction, CatalogRow } from './DirectoryFlowWorkspace';
import { catalogFilterOptions } from './CatalogFilters';
import RentalReviewDialog from '../rental/RentalReviewDialog';
import type { RentalReview } from '../rental/RentalAssociationReview';

type Kind = '' | 'admission' | 'auction' | 'rental';
type Issue = { kind: Exclude<Kind, ''>; reason: string; label: string; operation?: string; rental?: RentalReview; auction?: Auction };
export type PendingRow = { key: string; community_id: string | null; name: string; address: string; district: string; issues: Issue[] };
type Packet = { items: PendingRow[]; total: number; page: number; counts: Record<string, number>; default_pending_total: number };
const kindLabels = { '': '全部事项', admission: '小区收录', auction: '法拍关联', rental: '租金来源' };
const rentalLabels = { '': '全部租金待办', needs_selection: '待选择', search_failed: '查找失败', missing: '未找到', skipped: '已跳过' };
const operationLabels: Record<string, string> = { position: '地点待处理', use: '用途待确认', facts: '资料待补' };

export function PendingTable({ items, onProcess }: { items: PendingRow[]; onProcess: (row: PendingRow, issue: Issue) => void }) {
  return <div className="directory-table-wrap"><table className="review-table"><thead><tr>
    <th>小区 / 法拍房产</th><th>区域 / 地址</th><th>待处理事项</th><th>操作</th>
  </tr></thead><tbody>{items.map(row => <tr key={row.key}>
    <td data-label="小区 / 法拍房产">{row.name}</td>
    <td data-label="区域 / 地址">{row.district || '区域待核对'}<small>{row.address || '地址待补充'}</small></td>
    <td data-label="待处理事项">{row.issues.map(issue => <small key={issue.kind}>
      <strong>{kindLabels[issue.kind]}</strong> · {issue.operation && `${operationLabels[issue.operation]}：`}{issue.label}
    </small>)}</td>
    <td data-label="操作"><div className="directory-actions">{row.issues.map(issue => <button key={issue.kind} className="btn btn-secondary"
      onClick={() => onProcess(row, issue)}>{issue.kind === 'admission' ? '查看资料' : issue.kind === 'auction' ? '核对关联' :
        issue.reason === 'skipped' ? '恢复处理' : issue.reason === 'search_failed' ? '重试查找' : issue.reason === 'missing' ? '探查来源' : '核对来源'}</button>)}</div></td>
  </tr>)}</tbody></table></div>;
}

export default function PendingWorkspace({ initialKind = '', revision, active, onSelect, onAuction, onChanged, onCount, onSyncAuctions, busy }: {
  initialKind?: Kind; revision: number; active: boolean; onSelect: (row: CatalogRow) => void;
  onAuction: (row: Auction) => void; onChanged: () => void; onCount: (count: number) => void; onSyncAuctions: () => void; busy: boolean;
}) {
  const [kind, setKind] = useState<Kind>(initialKind);
  const [q, setQ] = useState('');
  const [district, setDistrict] = useState('滨江');
  const [status, setStatus] = useState('');
  const [operation, setOperation] = useState('');
  const [use, setUse] = useState('');
  const [skipped, setSkipped] = useState(false);
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [rental, setRental] = useState<RentalReview | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  useEffect(() => () => detailRequest.current?.abort(), []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q, district, kind, page: String(page), include_skipped: String(skipped),
          ...(kind === 'rental' ? { rental_status: status } : {}), ...(kind === 'admission' ? { operation, use } : {}) });
        const response = await fetch('/api/map/directory/workflow/pending?' + params, { signal: controller.signal });
        const value = await response.json();
        if (!response.ok || !value.success) throw new Error(value.detail || value.message || '待处理清单加载失败');
        if (controller.signal.aborted) return;
        const next = value.data as Packet;
        setPacket(next); setPage(next.page); onCount(next.default_pending_total); setError(''); setLoading(false);
      } catch (e) { if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : '加载失败'); setLoading(false); } }
    }, 200);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [active, q, district, kind, status, operation, use, skipped, page, revision, refresh, onCount]);
  useEffect(() => {
    const changed = () => { setLoading(true); setRefresh(v => v + 1); };
    window.addEventListener('housing-rental-data-changed', changed);
    return () => window.removeEventListener('housing-rental-data-changed', changed);
  }, []);
  function update(action: () => void) { detailRequest.current?.abort(); action(); setPage(1); setLoading(true); setError(''); }
  async function process(row: PendingRow, issue: Issue) {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    if (issue.rental) { setRental(issue.rental); return; }
    if (issue.auction) { onAuction(issue.auction); return; }
    try {
      const response = await fetch('/api/map/directory/workflow/catalog/' + encodeURIComponent(row.community_id || ''), { signal: controller.signal });
      const value = await response.json();
      if (!response.ok || !value.success) throw new Error(value.detail || '资料加载失败');
      if (!controller.signal.aborted) onSelect(value.data);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '资料加载失败'); }
  }
  return <section aria-label="统一待处理工作台">
    <div className="pending-toolbar">
      <label className="pending-search">搜索<input placeholder="小区名称、法拍名称或地址" value={q} onChange={e => update(() => setQ(e.target.value))} /></label>
      <label>处理事项<select value={kind} onChange={e => update(() => { setKind(e.target.value as Kind); setStatus(''); setOperation(''); setUse(''); })}>
        {Object.entries(kindLabels).map(([key, label]) => <option key={key} value={key}>{label}（{packet?.counts[key || 'all'] ?? '—'}）</option>)}
      </select></label>
      <label>区域<select value={district} onChange={e => update(() => setDistrict(e.target.value))}>{catalogFilterOptions('district').map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
      {kind === 'rental' && <label>租金状态<select value={status} onChange={e => update(() => setStatus(e.target.value))}>
        {Object.entries(rentalLabels).filter(([key]) => skipped || key !== 'skipped').map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>}
      {kind === 'admission' && <><label>待处理操作<select value={operation} onChange={e => update(() => setOperation(e.target.value))}>{catalogFilterOptions('operation').map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
        <label>用途核对<select value={use} onChange={e => update(() => setUse(e.target.value))}>{catalogFilterOptions('use').map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label></>}
      <label className="pending-skipped"><input type="checkbox" checked={skipped} onChange={e => update(() => { setSkipped(e.target.checked); setStatus(''); })} />包含已跳过</label>
      <button className="btn btn-secondary" onClick={() => update(() => setRefresh(v => v + 1))}>刷新清单</button>
      {kind === 'auction' && <button className="btn btn-secondary" disabled={busy || !active} onClick={onSyncAuctions}>同步历史法拍 / 重试</button>}
    </div>
    <p className="directory-muted">{loading ? '正在加载…' : `共 ${packet?.total ?? 0} 条待处理记录`} · 同一小区的事项合并展示，未关联法拍单独列出。未查询的租金来源可在“采集任务”中继续匹配。</p>
    {error && <p role="alert" className="directory-warning">{error}</p>}
    {!active ? <p className="directory-empty">名单流程尚未启用。</p> : loading ? <p role="status">加载待处理清单…</p> : !error && <>
      {packet?.items.length ? <PendingTable items={packet.items} onProcess={(...args) => void process(...args)} /> : <p className="directory-empty">没有符合条件的待处理记录。</p>}
      <nav className="directory-actions" aria-label="待处理分页"><button disabled={page <= 1} onClick={() => { setLoading(true); setPage(v => v - 1); }}>上一页</button>
        <span>第 {page} / {Math.max(1, Math.ceil((packet?.total || 0) / 30))} 页</span>
        <button disabled={page * 30 >= (packet?.total || 0)} onClick={() => { setLoading(true); setPage(v => v + 1); }}>下一页</button></nav>
    </>}
    {rental && <RentalReviewDialog key={rental.community_id} item={rental} onClose={() => setRental(null)} onChanged={() => { setLoading(true); setRefresh(v => v + 1); onChanged(); }} />}
  </section>;
}
