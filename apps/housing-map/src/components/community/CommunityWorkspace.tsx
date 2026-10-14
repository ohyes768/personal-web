'use client';

import { useEffect, useRef, useState } from 'react';
import AutoReviewPanel, { AutoEvidence, AutoReport } from './AutoReviewPanel';
import RentalAssociationReview from '../rental/RentalAssociationReview';
import { AdmissionControls, Community, Source, Report, DirectorySourceCard, labels, collectionLabels, phaseLabels, mapLabels, request, safeDirectoryLink } from './DirectoryCards';

type Review = { id: string; name: string; district?: string; address?: string; revision: number; state: string;
  existing_cid?: string; members: Source[]; sources: string[]; reasons: string[]; suggestions: Community[];
  auto_review_locked?: boolean; auction_assets: number; auction_rounds: number; auction_identity_uncertain: boolean;
  rounds?: { auction_id: string; title?: string; source_url?: string; round?: number }[] };
type Page<T> = { items: T[]; total: number };
type Summary = { residential: number; pending: number; excluded: number; auction_needs_sync: boolean };
type Confirmation = { path: string; body: object; text: string };

function Sites({ sites }: { sites: string[] }) { return <>{sites.map(site => <span className="directory-badge" key={site}>{labels[site] || site}</span>)}</>; }
export function CommunityTable({ items, onSelect }: { items: Community[]; onSelect: (id: string) => void }) {
  return <div className="directory-table-wrap"><table className="review-table"><thead><tr><th>名称 / 别名</th><th>区域 / 地址</th><th>物业类型 / 确认方式</th><th>资料来源</th><th>地图状态</th><th>操作</th></tr></thead><tbody>
    {items.map(c => <tr key={c.community_id}><td data-label="名称 / 别名"><strong>{c.community_name}</strong><small>{c.aliases?.join(' / ')}</small></td><td data-label="区域 / 地址">{c.district || '区域待核对'}<small>{c.address || '地址待补充'}</small></td>
      <td data-label="物业类型 / 确认方式">{c.effective_property_type}<small>{c.admission?.decision_kind === 'manual' ? '人工确认' : c.admission?.decision_kind === 'automatic' ? '自动收录' : '来源证据确认'}</small>{c.admission_conflict && <small className="directory-warning">新资料有疑点</small>}</td>
      <td data-label="资料来源"><Sites sites={[...new Set(c.sources?.map(r => r.source))]} /></td><td data-label="地图状态">{mapLabels[c.map_status || ''] || '待核对'}</td>
      <td data-label="操作"><button className="btn btn-secondary" onClick={() => onSelect(c.community_id)}>详情 / 管理</button></td></tr>)}
  </tbody></table></div>;
}
export function ReviewTable({ items, onSelect }: { items: Review[]; onSelect: (id: string) => void }) {
  return <div className="directory-table-wrap"><table className="review-table"><thead><tr><th>候选小区</th><th>区域 / 地址</th><th>类型线索</th><th>资料来源</th><th>待审核原因</th><th>疑似已有小区</th><th>操作</th></tr></thead><tbody>
    {items.map(r => <tr key={r.id}><td data-label="候选小区"><strong>{r.name}</strong><small>{r.members.length} 条来源资料</small></td><td data-label="区域 / 地址">{r.district || '未知'}<small>{r.address || '地址待核对'}</small></td>
      <td data-label="类型线索">{[...new Set(r.members.map(m => m.property_type).filter(Boolean))].join(' / ') || '用途待核实'}{r.members.some(m => m.source === 'amap') && <small>地图分类仅作线索</small>}</td>
      <td data-label="资料来源"><Sites sites={r.sources} />{r.sources.includes('laipai') && <small>{r.auction_assets} 个已知资产 · {r.auction_rounds} 条轮次{r.auction_identity_uncertain && ' · 资产编号缺失，总套数不确定'}</small>}</td>
      <td data-label="待审核原因">{r.reasons.join('；')}</td><td data-label="疑似已有小区">{r.suggestions.map(c => c.community_name).join(' / ') || '暂无建议'}</td>
      <td data-label="操作"><button className="btn btn-secondary" onClick={() => onSelect(r.id)}>{r.state === 'excluded' ? '查看 / 恢复' : '审核'}</button></td></tr>)}
  </tbody></table></div>;
}

function ReviewPanel({ review: r, busy, confirm }: { review: Review; busy: boolean; confirm: (value: Confirmation) => void }) {
  const [name, setName] = useState(r.name.includes('名称缺失') ? '' : r.name);
  const [reason, setReason] = useState('');
  const [type, setType] = useState('住宅');
  const [members, setMembers] = useState(r.members.map(m => m.id));
  const [query, setQuery] = useState('');
  const [targets, setTargets] = useState<Community[]>([]);
  const [target, setTarget] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => request<Page<Community>>(`/communities?admission_state=admitted&q=${encodeURIComponent(query)}&page_size=100`, 'GET', undefined, controller.signal)
      .then(d => { if (!controller.signal.aborted) setTargets(d.items.filter(c => c.community_id !== r.existing_cid)); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); }), 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, r.existing_cid]);
  const partial = members.length !== r.members.length;
  const decide = (action: string, text: string) => confirm({ path: `/reviews/${r.id}/decision`, body: { action, revision: r.revision, member_ids: members, name, property_type: type, reason, target_id: target || null }, text });
  return <div className="review-panel">
    <p className="directory-warning">{r.reasons.join('；')}</p>
    {r.auto_review_locked && <p className="directory-warning">人工审核锁已保留，更新资料不会自动收录。</p>}
    {r.auto_review_locked && r.state === 'pending' && <button className="btn btn-secondary" disabled={busy} onClick={() => confirm({ path: `/reviews/${r.id}/allow-auto-review`, body: { revision: r.revision }, text: '明确解除此候选的人工审核锁？只允许重新按规则判断，不立即收录。' })}>允许重新自动审核</button>}
    {r.state === 'excluded' ? <button className="btn btn-secondary" disabled={busy} onClick={() => confirm({ path: `/reviews/${r.id}/restore`, body: { revision: r.revision }, text: '恢复到待审核？仍保留人工审核锁，不直接进入住宅名单。' })}>恢复到待审核</button> : <>
      <div className="directory-edit-grid"><label>确认小区名称<input aria-label="确认小区名称" value={name} maxLength={100} onChange={e => setName(e.target.value)} /></label>
        <label>确认物业类型<select aria-label="确认物业类型" value={type} onChange={e => setType(e.target.value)}>{['住宅', '别墅', '排屋'].map(t => <option key={t}>{t}</option>)}</select></label>
        <label>审核理由<input aria-label="审核理由" value={reason} maxLength={300} placeholder="排除必填；其他操作可记录依据" onChange={e => setReason(e.target.value)} /></label></div>
      <p className="directory-muted">核对下面的来源成员。不同小区或分期先拆分，再分别审核。</p>
      <div className="directory-actions"><button className="btn btn-primary" disabled={busy || !name.trim() || partial} onClick={() => decide('admit', `确认“${name}”是住宅小区，并收录全部 ${members.length} 条来源？地图只显示坐标有效的小区。`)}>收录为住宅小区</button>
        <button className="btn btn-secondary" disabled={busy || !reason.trim() || partial} onClick={() => decide('exclude', '排除这个候选的住宅收录？来源资料和法拍轮次保留，可恢复待审核。')}>排除收录</button>
        <button className="btn btn-secondary" disabled={busy || !members.length || !partial} onClick={() => confirm({ path: `/reviews/${r.id}/split`, body: { revision: r.revision, member_ids: members }, text: '将勾选成员拆成独立候选？不会自动合并回来；若已有主档关联，会解除这些成员与原主档的关联。' })}>拆分所选成员</button></div>
      <div className="directory-linker"><h4>合并到已有住宅小区</h4><input aria-label="搜索已有住宅" placeholder="搜索名称或别名" value={query} onChange={e => { setQuery(e.target.value); setTarget(''); }} />
        <select aria-label="合并目标住宅" value={target} onChange={e => setTarget(e.target.value)}><option value="">选择已收录住宅</option>{targets.map(c => <option key={c.community_id} value={c.community_id}>{c.community_name} · {c.address}</option>)}</select>
        <button className="btn btn-secondary" disabled={busy || !target || partial} onClick={() => decide('merge', '确认全部候选成员属于所选住宅、同一分期？只补充已有住宅，不增加住宅数量。')}>合并至已有住宅</button></div>
      {error && <p role="alert">{error}</p>}
    </>}
    <h4>原始来源与证据</h4>
    {r.members.map(m => <div key={m.id}>{r.state !== 'excluded' && <label className="review-member"><input type="checkbox" checked={members.includes(m.id)} onChange={e => setMembers(v => e.target.checked ? [...v, m.id] : v.filter(id => id !== m.id))} />一起审核：{labels[m.source]} · {m.name}</label>}<DirectorySourceCard item={m} /></div>)}
    {!!r.rounds?.length && <details><summary>法拍记录（{r.rounds.length} 条轮次）</summary>{r.rounds.map(round => <p key={round.auction_id}>{round.title} · 第{round.round || '?'}轮 {safeDirectoryLink(round.source_url) && <a href={round.source_url} target="_blank" rel="noopener noreferrer">原始法拍资料 ↗</a>}</p>)}</details>}
  </div>;
}

function MasterPanel({ community: c, busy, changed, confirm }: { community: Community; busy: boolean; changed: (path: string, method: string, body?: object) => Promise<void>; confirm: (value: Confirmation) => void }) {
  const [name, setName] = useState(c.community_name);
  const [aliases, setAliases] = useState(c.aliases?.join('、') || '');
  const [address, setAddress] = useState(c.address || '');
  return <><div className="directory-edit-grid"><label>标准小区名称<input value={name} onChange={e => setName(e.target.value)} maxLength={100} /></label>
    <label>别名<input value={aliases} onChange={e => setAliases(e.target.value)} /></label><label>地址<input value={address} onChange={e => setAddress(e.target.value)} /></label></div>
    <button className="btn btn-secondary" disabled={busy || !name.trim()} onClick={() => void changed(`/communities/${c.community_id}`, 'PUT', { name, aliases: aliases.split(/[、,，]/).filter(Boolean), address, district: c.district })}>保存名称与资料</button>
    <AdmissionControls community={c} busy={busy} onDecision={(action, body, text) => confirm({ path: `/communities/${c.community_id}/${action}`, body, text })} />
    {c.admission?.decision_kind === 'automatic' && <details><summary>自动收录依据（可用上方“移到待审核”撤销）</summary><p>{c.admission.reason} · {c.admission.decided_at}</p><p>规则：{c.admission.rule_version}</p><AutoEvidence evidence={c.admission.evidence || []} /></details>}
    <details><summary>原始来源与关联管理</summary>{c.sources?.map(m => <DirectorySourceCard key={m.id} item={m}><button className="btn btn-secondary" disabled={busy} onClick={() => void changed(`/sources/${m.id}/associate`, 'DELETE')}>解除此来源关联</button></DirectorySourceCard>)}</details>
    <details><summary>合并重复小区</summary><p>先“移到待审核”，在审核详情中选择已有住宅合并，保留历史身份和别名。</p></details>
    <details><summary>操作记录</summary>{c.events?.map(e => <p key={e.seq} className="directory-muted">{e.created_at.slice(0, 19)} · {e.action} · {e.payload.reason}</p>)}</details></>;
}

export default function CommunityWorkspace({ onChanged, initialSource = '' }: { onChanged: () => void; initialSource?: string }) {
  const [mode, setMode] = useState(initialSource ? 'reviews' : 'residential');
  const [q, setQ] = useState(''); const [district, setDistrict] = useState('滨江');
  const [source, setSource] = useState(initialSource); const [state, setState] = useState('pending');
  const [propertyType, setPropertyType] = useState('');
  const [page, setPage] = useState(1); const [revision, setRevision] = useState(0);
  const [masters, setMasters] = useState<Community[]>([]); const [reviews, setReviews] = useState<Review[]>([]);
  const [total, setTotal] = useState(0); const [counts, setCounts] = useState({ residential: 0, pending: 0 });
  const [summary, setSummary] = useState<Summary | null>(null);
  const [report, setReport] = useState<Report | null>(null); const previousRunning = useRef(false);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<{ kind: string; id: string } | null>(null);
  const [detail, setDetail] = useState<Community | Review | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null); const dialog = useRef<HTMLDialogElement>(null);
  const [collectionSources, setCollectionSources] = useState(['tmsf', 'amap']);
  useEffect(() => { if (confirmation) dialog.current?.showModal(); }, [confirmation]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      const filter = new URLSearchParams({ q, district, source, page: String(page), page_size: '30' });
      try {
        const [res, rev, pending, inventory] = await Promise.all([
          request<Page<Community>>(`/communities?${filter}&admission_state=admitted&property_type=${encodeURIComponent(propertyType)}`, 'GET', undefined, controller.signal),
          request<Page<Review>>(`/reviews?${filter}&state=${state}`, 'GET', undefined, controller.signal),
          state === 'pending' ? Promise.resolve(null) : request<Page<Review>>(`/reviews?${filter}&state=pending`, 'GET', undefined, controller.signal),
          request<Summary>('/summary', 'GET', undefined, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        const currentTotal = mode === 'residential' ? res.total : rev.total;
        if (page > 1 && (page - 1) * 30 >= currentTotal) { setPage(Math.max(1, Math.ceil(currentTotal / 30))); return; }
        setMasters(res.items); setReviews(rev.items); setTotal(currentTotal); setCounts({ residential: res.total, pending: pending?.total ?? rev.total }); setSummary(inventory); setError('');
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '列表加载失败'); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [q, district, source, state, propertyType, page, mode, revision]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    request<Community | Review>(`/${selected.kind}/${encodeURIComponent(selected.id)}`, 'GET', undefined, controller.signal)
      .then(d => { if (!controller.signal.aborted) setDetail(d); })
      .catch(e => { if (!controller.signal.aborted) { setDetail(null); setError(e.message); } });
    return () => controller.abort();
  }, [selected, revision]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<Report | null>('/collection', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (previousRunning.current && !next?.running) setRevision(v => v + 1);
        previousRunning.current = !!next?.running; setReport(next);
      } catch { /* List actions surface errors; polling never masks the working directory. */ }
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  async function act(path: string, method = 'POST', body?: object) {
    setBusy(true); setError('');
    try {
      await request(path, method, body); setConfirmation(null); setSelected(null); setDetail(null); setRevision(v => v + 1); onChanged(); setNotice('操作已保存，住宅名单、审核队列和地图已更新。');
    } catch (e) { setConfirmation(null); setRevision(v => v + 1); setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  }
  const select = (kind: string, id: string) => { setSelected({ kind, id }); setDetail(null); };
  const master = detail && 'community_name' in detail ? detail : null;
  const review = detail && 'members' in detail ? detail : null;
  const filterChanged = () => { setLoading(true); setPage(1); setSelected(null); setDetail(null); };
  return <section className="directory-page review-workspace" aria-label="小区数据管理">
    <header className="review-heading"><div><p className="review-eyebrow">小区库存</p><h2>住宅名单与人工审核</h2><p className="directory-muted">住宅是地图的数据来源；有疑点的候选在审核后收录、合并或排除。</p></div>
      <p className="review-inventory">全部区域：住宅 <strong>{summary?.residential ?? '—'}</strong> · 待审核 <strong>{summary?.pending ?? '—'}</strong> · 已排除 {summary?.excluded ?? '—'}</p></header>
    <details className="review-collection" open={report?.running || undefined}><summary>最近一次来源采集{report && ` · ${phaseLabels[report.phase] || report.phase}`}</summary><div className="directory-collection">
      <div className="directory-actions">{Object.entries(collectionLabels).map(([key, label]) => <label key={key}><input type="checkbox" checked={collectionSources.includes(key)} onChange={e => setCollectionSources(v => e.target.checked ? [...v, key] : v.filter(k => k !== key))} />{label}</label>)}
        <button className="btn btn-primary" disabled={busy || report?.running || !collectionSources.length} onClick={() => void act('/collection', 'POST', { sources: collectionSources })}>采集名称与物业类型</button>
        {report?.running && <button className="btn btn-secondary" onClick={() => void act('/collection', 'DELETE')}>取消采集</button>}</div>
      <p className="directory-muted">下方是本次来源记录条数，不是小区库存。失败或截断不代表采全。自动收录需先预演、核对并明确启用。</p>
      {report ? <div><p>采集时间：{report.finished_at || report.started_at || '暂无'}（来源报告时间）</p><p>{phaseLabels[report.phase]} · 新来源 {report.new || 0} · 已有来源 {report.existing || 0} · 已关联 {report.matched || 0} · 待关联 {report.pending || 0} · 跳过 {report.ignored || 0}</p>
        <p>透明售房网类型：获取 {report.property_types || 0} · 复用 {report.property_types_cached || 0} · 失败 {report.property_types_failed || 0}</p>
        {report.coverage?.amap && <p>高德：{report.coverage.amap.unique} 个地点 · 过滤 {report.coverage.amap.filtered} · 去重 {report.coverage.amap.duplicates} · {report.coverage.amap.complete ? '区域查询结束' : '区域查询未全部完成'}</p>}
        {[...(report.errors || []), ...(report.truncated || [])].map((e, i) => <p className="directory-warning" key={i}>{labels[e.source]}：{e.message}</p>)}</div> : <p>暂无来源采集记录。</p>}
      {report?.auto_review && <details><summary>本轮自动审核（单独统计）</summary><AutoReport report={report.auto_review} /></details>}
    </div></details>
    <AutoReviewPanel refreshVersion={revision} onChanged={() => { setRevision(v => v + 1); onChanged(); }} />
    <div className="review-tabs"><button aria-pressed={mode === 'residential'} onClick={() => { if (mode !== 'residential') { setMode('residential'); filterChanged(); } }}>住宅小区（{counts.residential}）</button><button aria-pressed={mode === 'reviews'} onClick={() => { if (mode !== 'reviews') { setMode('reviews'); filterChanged(); } }}>待审核小区（{counts.pending}）</button></div>
    <div className="directory-toolbar"><input aria-label="搜索小区名称" placeholder="搜索名称、别名、地址" value={q} onChange={e => { setQ(e.target.value); filterChanged(); }} />
      <select aria-label="目录区域" value={district} onChange={e => { setDistrict(e.target.value); filterChanged(); }}><option value="滨江">滨江区</option><option value="萧山">萧山接壤目录</option><option value="">全部区域</option></select>
      <select aria-label="数据来源" value={source} onChange={e => { setSource(e.target.value); filterChanged(); }}><option value="">全部来源</option>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      {mode === 'reviews' && <select aria-label="审核状态" value={state} onChange={e => { setState(e.target.value); filterChanged(); }}><option value="pending">待审核</option><option value="excluded">已排除（可恢复）</option></select>}
      {mode === 'residential' && <select aria-label="住宅物业类型" value={propertyType} onChange={e => { setPropertyType(e.target.value); filterChanged(); }}><option value="">全部住宅类型</option>{['住宅', '别墅', '排屋'].map(t => <option key={t}>{t}</option>)}</select>}
      <button className="btn btn-secondary" disabled={busy} onClick={() => void act('/reviews/sync')}>同步历史法拍 / 重试</button></div>
    {summary?.auction_needs_sync && <p className="directory-warning">有已保存法拍尚未同步到审核目录，可点击“同步历史法拍 / 重试”。</p>}
    {error && <p role="alert" className="directory-warning">{error} <button onClick={() => setRevision(v => v + 1)}>刷新重试</button></p>}{notice && <p role="status">{notice}</p>}
    <div className="directory-workspace"><div className="directory-list-panel"><p className="directory-muted">{loading ? '正在更新当前筛选…' : <>当前筛选：{total} 个{mode === 'residential' ? '住宅小区' : state === 'excluded' ? '已排除候选' : '待审核小区'}；每个小区候选一行。</>}</p>
      {loading ? <p role="status">加载小区名单…</p> : mode === 'residential' ? <CommunityTable items={masters} onSelect={id => select('communities', id)} /> : <ReviewTable items={reviews} onSelect={id => select('reviews', id)} />}
      {!loading && total === 0 && <p className="directory-empty">没有符合条件的小区。</p>}
      <nav className="directory-actions" aria-label="小区名单分页"><button className="btn btn-secondary" disabled={page === 1 || loading} onClick={() => setPage(v => v - 1)}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(total / 30))} 页 · 共 {total} 个</span><button className="btn btn-secondary" disabled={page * 30 >= total || loading} onClick={() => setPage(v => v + 1)}>下一页</button></nav>
    </div>{selected && <aside className="directory-detail"><div className="directory-source-heading"><h3>{master?.community_name || review?.name || '加载详情…'}</h3><button className="btn btn-secondary" onClick={() => { setSelected(null); setDetail(null); }}>关闭</button></div>
      {master && <MasterPanel key={`${master.community_id}-${master.admission?.revision}`} community={master} busy={busy} changed={act} confirm={setConfirmation} />}
      {review && <ReviewPanel key={`${review.id}-${review.revision}`} review={review} busy={busy} confirm={setConfirmation} />}</aside>}</div>
    <details className="review-rental"><summary>租金来源待处理（独立业务清单）</summary><p className="directory-muted">这里处理已收录小区缺少租金来源的问题，不计入待审核小区库存。</p><RentalAssociationReview onChanged={() => { setRevision(v => v + 1); onChanged(); }} /></details>
    {confirmation && <dialog ref={dialog} className="directory-confirm" aria-label="确认审核操作" onCancel={() => setConfirmation(null)}><p>{confirmation.text}</p><div className="directory-actions"><button autoFocus className="btn btn-primary" disabled={busy} onClick={() => void act(confirmation.path, 'POST', confirmation.body)}>确认操作</button><button className="btn btn-secondary" disabled={busy} onClick={() => setConfirmation(null)}>返回核对</button></div></dialog>}
  </section>;
}
