'use client';

import { useEffect, useRef, useState } from 'react';
import { Community, Source, DirectorySourceCard, marketLabels, mapLabels, safeDirectoryLink } from './DirectoryCards';
import PositionPanel, { Position, PositionBadge, positionLabels } from './PositionPanel';
import RentalAssociationReview from '../rental/RentalAssociationReview';

type CatalogRow = Community & { property_types?: string[]; position?: Position; qualification: string; facts_state: string; exclusion_reason: string;
  source_record_id?: string; geographic_address?: string; coordinate_evidence?: { source_id?: string; captured_at?: string } };
type Auction = Source & { revision: string; skipped: boolean; candidates: Community[]; reason: string;
  auction_ids?: string[]; rounds?: { auction_id: string; title?: string; source_url?: string; round?: number }[] };
type Summary = { active: boolean; admitted: number; excluded: number; auction_pending: number };
type Page<T> = { items: T[]; total: number; page: number; property_types?: string[] };
type Job = { running: boolean; phase: string; finished_at?: string; started_at?: string; processed?: number; total?: number;
  matched?: number; new?: number; existing?: number; updated?: number; skipped?: number; error?: string;
  stage?: string; association?: { checked?: number; matched?: number; pending?: number; missing?: number; failed?: number; deferred?: number }; errors?: { message: string; name?: string }[]; truncated?: { message: string }[] };
type IncomingJob = Omit<Job, 'errors'> & { total_communities?: number; processed_communities?: number;
  errors?: Job['errors'] | { items?: { message: string }[]; total?: number } };
export function normalizeCollectionJob(value: IncomingJob | null): Job | null {
  if (!value) return null;
  return { ...value, total: value.total ?? value.total_communities, processed: value.processed ?? value.processed_communities,
    errors: Array.isArray(value.errors) ? value.errors : value.errors?.items || [] };
}
const tasks = [
  { id: 'tmsf', label: '采集透明售房网', path: '/directory/collection', hint: '采集名单、用途和挂牌数量，自动分类收录', body: { sources: ['tmsf'] } },
  { id: 'amap', label: '高德信息采集', path: '/directory/workflow/positions', hint: '仅已收录住宅；批量补待补全和失败项，保留人工结果' },
  { id: 'rent', label: '租金信息采集', path: '/rentals/refresh', hint: '仅已收录住宅；复用关联，更新房天下租金' },
  { id: 'auction', label: '法拍数据采集', path: '/auctions/refresh', hint: '采集滨江法拍，匹配住宅，未匹配进入待关联' },
];
const phases: Record<string, string> = { running: '正在采集', crawling: '正在采集', publishing: '正在发布', checking_sources: '检查来源', idle: '尚未采集',
  succeeded: '采集完成', done: '采集完成', failed: '采集失败', error: '采集失败', partial_failed: '部分完成',
  cancelled: '已取消', interrupted: '服务重启，采集中断', cancelling: '正在取消' };

export async function workflowRequest<T>(path: string, method = 'GET', body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/map' + path, { method, signal,
    headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const packet = await response.json();
  if (!response.ok || packet.success === false) throw new Error(typeof packet.detail === 'string' ? packet.detail : packet.message || packet.error || '请求失败，请重试');
  return packet.data as T;
}

export function CollectionControls({ active, jobs, errors, busy, action }: { active: boolean; jobs: Record<string, Job | null>;
  errors: Record<string, string>; busy: boolean; action: (path: string, method: string, body?: object) => void }) {
  return <div className="directory-task-grid">{tasks.map(t => {
    const job = jobs[t.id];
    return <article className="directory-task-card" key={t.id}>
      <strong>{t.label}</strong><p className="directory-muted">{t.hint}</p>
      <div className="directory-actions"><button className="btn btn-primary" disabled={!active || busy || job?.running}
        onClick={() => action(t.path, 'POST', t.body)}>{job?.running ? '正在采集…' : t.id === 'amap' ? '批量补全高德定位' : t.label}</button>
        {job?.running && <button className="btn btn-secondary" disabled={busy} onClick={() => action(t.path, 'DELETE')}>取消采集</button>}</div>
      {job?.stage && <p className="directory-muted">{({ checking: '检查租金来源', discovering: '查找租金来源', crawling: '采集租金房源', publishing: '发布租金统计', names: '更新小区名录', property_types: '补充用途资料' } as Record<string, string>)[job.stage] || '更新来源资料'}</p>}
      {job?.association && <p className="directory-muted">已检查 {job.association.checked || 0} · 已关联 {job.association.matched || 0} · 待选择 {job.association.pending || 0} · 未找到 {job.association.missing || 0} · 查询失败 {job.association.failed || 0} · 未查询 {job.association.deferred || 0}</p>}
      {job && <p role="status">{phases[job.phase] || job.phase}
        {job.processed !== undefined && ` · 已处理 ${job.processed}${job.total !== undefined ? ` / ${job.total}` : ''}`}
        {job.new !== undefined && ` · 新来源 ${job.new} · 已有 ${job.existing || 0}`}
        {job.updated !== undefined && ` · 补全 ${job.updated} · 跳过 ${job.skipped || 0}`}
        {job.matched !== undefined && t.id === 'auction' && ` · 本次法拍 ${job.matched} 条`}</p>}
      {job?.finished_at && <small>上次结束：{job.finished_at.slice(0, 19).replace('T', ' ')}（UTC）</small>}
      {(errors[t.id] || job?.error) && <p role="alert" className="directory-warning">{errors[t.id] || job?.error}</p>}
      {!!(job?.errors?.length || job?.truncated?.length) && <details><summary>本轮未完成事项（可重试）</summary>
        {[...(job?.errors || []), ...(job?.truncated || [])].map((e, i) => <p className="directory-warning" key={i}>{'name' in e && e.name ? `${e.name}：` : ''}{e.message}</p>)}</details>}
    </article>;
  })}</div>;
}

export function CatalogClassificationFilter({ mode, value, propertyTypes, onChange }: {
  mode: string; value: string; propertyTypes: string[]; onChange: (value: string) => void;
}) {
  if (mode === 'auctions') return null;
  if (mode === 'admitted') return <select aria-label="新房二手房筛选" value={value} onChange={e => onChange(e.target.value)}>
    <option value="">全部</option><option value="new_house">新房</option><option value="second_hand">二手房</option>
  </select>;
  const options = [...new Set(['住宅', '其他', '写字楼', ...propertyTypes, ...(value && value !== '__missing__' ? [value] : [])])];
  return <select aria-label="不收录用途筛选" value={value} onChange={e => onChange(e.target.value)}>
    <option value="">全部用途</option>{options.map(prop => <option key={prop} value={prop}>{prop}</option>)}
    <option value="__missing__">用途资料缺失</option>
  </select>;
}

export function CatalogTable({ items, excluded, select, retry, busy, position }: { items: CatalogRow[]; excluded: boolean;
  select: (row: CatalogRow) => void; retry: (row: CatalogRow) => void; busy: boolean; position?: (row: CatalogRow) => void }) {
  return <div className="directory-table-wrap"><table className="review-table"><thead><tr>
    <th>小区名称</th><th>区域 / 实际地址</th><th>用途 / 市场</th><th>{excluded ? '不收录原因 / 资料状态' : '地图定位'}</th>{!excluded && <th>高德定位</th>}<th>操作</th>
  </tr></thead><tbody>{items.map(c => <tr key={c.community_id}>
    <td data-label="小区名称"><strong>{c.community_name}</strong><small>{c.aliases?.join(' / ')}</small></td>
    <td data-label="区域 / 实际地址">{c.district || '区域待补'}<small>{c.address || '实际地址待补充'}</small></td>
    <td data-label="用途 / 市场">{c.property_types?.join(' / ') || c.effective_property_type || [...new Set(c.sources?.filter(s => s.source === 'tmsf').map(s => s.property_type).filter(Boolean))].join(' / ') || '用途资料缺失'}<small>{marketLabels[c.market_state || 'unknown']}</small></td>
    <td data-label={excluded ? '不收录原因 / 资料状态' : '地图定位'}>{excluded ? <>{c.exclusion_reason}<small>{c.facts_state === 'incomplete' ? '资料待补，可重新获取' : '条件不符'}</small></> : mapLabels[c.map_status || ''] || '位置待补全'}</td>
    {!excluded && <td data-label="高德定位"><PositionBadge position={c.position} /><button className="btn btn-secondary" disabled={busy} onClick={() => (position || select)(c)}>{c.position?.state === 'review' ? '确认位置' : ['matched', 'manual'].includes(c.position?.state || '') ? '查看定位' : '补全 / 重试'}</button></td>}
    <td data-label="操作"><button className="btn btn-secondary" onClick={() => select(c)}>查看资料</button>{excluded && <button className="btn btn-secondary" disabled={busy} onClick={() => retry(c)}>更新资料</button>}</td>
  </tr>)}</tbody></table></div>;
}

function AuctionPanel({ row, busy, action }: { row: Auction; busy: boolean;
  action: (path: string, method: string, body: object) => void }) {
  const [target, setTarget] = useState(''); const [keyword, setKeyword] = useState('');
  const [targets, setTargets] = useState<Community[]>(row.candidates);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      workflowRequest<Page<Community>>(`/directory/workflow/catalog?state=admitted&page_size=100&q=${encodeURIComponent(keyword)}`, 'GET', undefined, controller.signal)
        .then(p => { if (!controller.signal.aborted) { setTargets(p.items); setError(''); } })
        .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [keyword]);
  const send = (kind: string) => action(`/directory/workflow/auctions/${encodeURIComponent(row.id)}`, 'POST',
    { revision: row.revision, action: kind, ...(kind === 'bind' ? { community_id: target } : {}) });
  return <><p>{row.address || '法拍地址缺失'}</p><p className="directory-warning">{row.reason}</p>
    {safeDirectoryLink(row.source_url) && <a href={row.source_url} target="_blank" rel="noopener noreferrer">查看来拍呀原文 ↗</a>}
    <p>房产来源 ID：{row.source_id} · {row.auction_ids?.length || 0} 条拍卖轮次</p>
    {row.rounds?.map(r => <p key={r.auction_id}>{r.round ? `第${r.round}轮 · ` : ''}{r.title || r.auction_id}</p>)}
    <label>搜索已收录小区<input value={keyword} onChange={e => { setKeyword(e.target.value); setTarget(''); }} /></label>
    <label>关联到<select value={target} onChange={e => setTarget(e.target.value)}><option value="">请选择已收录小区</option>
      {targets.map(c => <option value={c.community_id} key={c.community_id}>{c.community_name} · {c.address || '地址待核对'}</option>)}</select></label>
    <p className="directory-muted">这里只建立法拍关联；找不到目标时可先跳过，不会新增住宅。</p>
    {error && <p role="alert">{error}</p>}
    <div className="directory-actions"><button className="btn btn-primary" disabled={busy || !target} onClick={() => send('bind')}>确认关联</button>
      <button className="btn btn-secondary" disabled={busy} onClick={() => send(row.skipped ? 'reopen' : 'skip')}>{row.skipped ? '重新处理' : '暂时跳过'}</button></div></>;
}

export default function DirectoryFlowWorkspace({ onChanged, initialSource = '' }: { onChanged: () => void; initialSource?: string }) {
  const [mode, setMode] = useState(initialSource === 'laipai' ? 'auctions' : 'admitted');
  const [q, setQ] = useState(''); const [district, setDistrict] = useState('滨江'); const [page, setPage] = useState(1);
  const [positionFilter, setPositionFilter] = useState('');
  const [marketFilter, setMarketFilter] = useState('');
  const [propertyFilter, setPropertyFilter] = useState('');
  const [propertyTypes, setPropertyTypes] = useState<string[]>([]);
  const [showSkipped, setShowSkipped] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null); const [items, setItems] = useState<CatalogRow[]>([]);
  const [auctions, setAuctions] = useState<Auction[]>([]); const [total, setTotal] = useState(0);
  const [jobs, setJobs] = useState<Record<string, Job | null>>({}); const [jobErrors, setJobErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  const [detail, setDetail] = useState<CatalogRow | null>(null); const [auction, setAuction] = useState<Auction | null>(null);
  const detailVersion = useRef(0);
  const finishes = useRef<Record<string, string>>({});
  const changed = () => { detailVersion.current += 1; setRevision(v => v + 1); setDetail(null); setAuction(null); onChanged(); };
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const counts = await workflowRequest<Summary>(`/directory/workflow/summary?${new URLSearchParams({ q, district })}`, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setSummary(counts);
        if (!counts.active) { setLoading(false); return; }
        const path = mode === 'auctions' ? `/directory/workflow/auctions?${new URLSearchParams({ q, page: String(page), include_skipped: String(showSkipped) })}`
          : `/directory/workflow/catalog?${new URLSearchParams({ q, district, state: mode, page: String(page), position: mode === 'admitted' ? positionFilter : '', market: mode === 'admitted' ? marketFilter : '', property_type: mode === 'excluded' ? propertyFilter : '' })}`;
        const packet = await workflowRequest<Page<CatalogRow> | Page<Auction>>(path, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (page > 1 && (page - 1) * 30 >= packet.total) { setPage(Math.max(1, Math.ceil(packet.total / 30))); return; }
        if (mode === 'auctions') setAuctions((packet as Page<Auction>).items); else setItems((packet as Page<CatalogRow>).items);
        if (mode === 'excluded') setPropertyTypes(packet.property_types || []);
        setTotal(packet.total); setError(''); setLoading(false);
      } catch (e) { if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : '名单加载失败'); setLoading(false); } }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [mode, q, district, page, showSkipped, revision, positionFilter, marketFilter, propertyFilter]);
  useEffect(() => {
    if (!summary?.active) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await Promise.allSettled(tasks.map(async t => {
        try {
          const next = normalizeCollectionJob(await workflowRequest<IncomingJob | null>(t.path, 'GET', undefined, controller.signal));
          if (controller.signal.aborted) return;
          setJobs(v => ({ ...v, [t.id]: next })); setJobErrors(v => ({ ...v, [t.id]: '' }));
          const mark = next?.finished_at || '';
          if (mark && finishes.current[t.id] !== undefined && finishes.current[t.id] !== mark) {
            setRevision(v => v + 1); onChanged();
          }
          finishes.current[t.id] = mark;
        } catch (e) { if (!controller.signal.aborted) setJobErrors(v => ({ ...v, [t.id]: e instanceof Error ? e.message : '状态查询失败' })); }
      }));
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [summary?.active, onChanged]);
  async function action(path: string, method: string, body?: object) {
    setBusy(true); setError(''); setNotice('');
    try {
      const outcome = await workflowRequest<{ errors?: string[] } | null>(path, method, body);
      setNotice(outcome?.errors?.length ? `部分资料已保存：${outcome.errors.join('；')}` : path.endsWith('/retry') ? '资料已更新，名单已重新分类。' : '操作已受理，采集结果请查看对应进度。');
      changed();
      const task = tasks.find(t => t.path === path);
      if (task) {
        const next = normalizeCollectionJob(await workflowRequest<IncomingJob | null>(path));
        setJobs(v => ({ ...v, [task.id]: next }));
      }
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); setRevision(v => v + 1); }
    finally { setBusy(false); }
  }
  function changeMode(value: string) { setMode(value); setPage(1); setLoading(true); setDetail(null); setAuction(null); detailVersion.current += 1; }
  async function select(row: CatalogRow) {
    const version = ++detailVersion.current;
    setDetail(row); setAuction(null);
    try {
      const path = `/directory/workflow/catalog/${encodeURIComponent(row.community_id)}`;
      const value = await workflowRequest<CatalogRow>(path);
      if (value.admission_state === 'admitted') value.position = await workflowRequest<Position>(path + '/position');
      if (detailVersion.current === version) setDetail(value);
    }
    catch (e) { setError(e instanceof Error ? e.message : '详情加载失败'); }
  }
  async function positionAction(kind: 'query' | 'confirm', body?: object) {
    if (!detail) return;
    const cid = detail.community_id; const version = detailVersion.current;
    setBusy(true); setError('');
    try {
      const position = await workflowRequest<Position>(`/directory/workflow/catalog/${encodeURIComponent(cid)}/position/${kind}`, 'POST', body);
      const fresh = await workflowRequest<CatalogRow>(`/directory/workflow/catalog/${encodeURIComponent(cid)}`);
      if (detailVersion.current === version) setDetail({ ...fresh, position });
      setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '定位操作失败，请刷新'); }
    finally { setBusy(false); }
  }
  return <section className="directory-page review-workspace" aria-label="小区数据管理">
    <header className="review-heading"><div><p className="review-eyebrow">小区数据管理</p><h2>住宅名单与数据采集</h2>
      <p className="directory-muted">先采集透明售房网并自动分类，再按需补全定位和租金；法拍无法匹配时人工关联。</p></div></header>
    {summary?.active === false && <p role="alert" className="directory-warning">新版名单流程尚未启用。需先备份线上数据并核对迁移预演；旧小区和历史数据不会自动删除或重置。</p>}
    <CollectionControls active={!!summary?.active} jobs={jobs} errors={jobErrors} busy={busy} action={(...args) => void action(...args)} />
    <div className="review-tabs">{[['admitted', '已收录', summary?.admitted], ['excluded', '不收录', summary?.excluded], ['auctions', '法拍待关联', summary?.auction_pending]].map(([key, label, count]) =>
      <button key={key} aria-pressed={mode === key} onClick={() => changeMode(String(key))}>{label}（{count ?? '—'}）</button>)}</div>
    <div className="directory-toolbar"><input aria-label="搜索小区名称" placeholder="搜索小区名称、地址" value={q} onChange={e => { setQ(e.target.value); setPage(1); setLoading(true); }} />
      {mode !== 'auctions' && <select aria-label="目录区域" value={district} onChange={e => { setDistrict(e.target.value); setPage(1); setLoading(true); }}><option value="滨江">滨江区</option><option value="萧山">萧山接壤目录</option><option value="">全部区域</option></select>}
      <CatalogClassificationFilter mode={mode} value={mode === 'admitted' ? marketFilter : propertyFilter} propertyTypes={propertyTypes}
        onChange={value => { if (mode === 'admitted') setMarketFilter(value); else setPropertyFilter(value); setPage(1); setLoading(true); }} />
      {mode === 'admitted' && <select aria-label="高德定位状态" value={positionFilter} onChange={e => { setPositionFilter(e.target.value); setPage(1); setLoading(true); }}><option value="">全部定位状态</option>{Object.entries(positionLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}
      {mode === 'auctions' && <label><input type="checkbox" checked={showSkipped} onChange={e => { setShowSkipped(e.target.checked); setPage(1); }} />包含已跳过</label>}
      <button className="btn btn-secondary" onClick={() => { setLoading(true); setRevision(v => v + 1); }}>刷新名单</button>
      {mode === 'auctions' && <button className="btn btn-secondary" disabled={busy || !summary?.active} onClick={() => void action('/auctions/associations/sync', 'POST')}>同步历史法拍 / 重试</button>}</div>
    {error && <p role="alert" className="directory-warning">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="directory-workspace"><div className="directory-list-panel">
      {loading ? <p role="status">加载名单…</p> : summary?.active && <><p className="directory-muted">当前筛选：{total} 条</p>
        {mode !== 'auctions' ? <CatalogTable items={items} excluded={mode === 'excluded'} select={row => void select(row)}
          retry={row => void action(`/directory/workflow/catalog/${encodeURIComponent(row.community_id)}/retry`, 'POST')} busy={busy || !!jobs.amap?.running} position={row => void select(row)} />
          : <div className="directory-table-wrap"><table className="review-table"><thead><tr><th>法拍房产</th><th>地址</th><th>待关联原因</th><th>操作</th></tr></thead><tbody>{auctions.map(r => <tr key={r.id}>
            <td data-label="法拍房产">{r.name}<small>{r.auction_ids?.length || 0} 条轮次{r.skipped ? ' · 已跳过' : ''}</small></td><td data-label="地址">{r.address || '暂无地址'}</td><td data-label="待关联原因">{r.reason}</td>
            <td data-label="操作"><button className="btn btn-secondary" onClick={() => { setAuction(r); setDetail(null); }}>核对关联</button></td></tr>)}</tbody></table></div>}
        {total === 0 && <p className="directory-empty">没有符合条件的记录。</p>}
        <nav className="directory-actions" aria-label="小区名单分页"><button disabled={page === 1} onClick={() => { setPage(v => v - 1); setLoading(true); }}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(total / 30))} 页</span><button disabled={page * 30 >= total} onClick={() => { setPage(v => v + 1); setLoading(true); }}>下一页</button></nav></>}
    </div>{(detail || auction) && <aside className="directory-detail"><div className="directory-source-heading"><h3>{detail?.community_name || auction?.name}</h3><button className="btn btn-secondary" onClick={() => { detailVersion.current += 1; setDetail(null); setAuction(null); }}>关闭</button></div>
      {auction && <AuctionPanel key={`${auction.id}-${auction.revision}`} row={auction} busy={busy} action={(...args) => void action(...args)} />}
      {detail && <><p>透明售房网实际地址：{detail.address || '待补充'}</p><p>高德地图地址：{detail.position?.selected?.address || detail.geographic_address || '待补全'}</p>
        {detail.exclusion_reason && <p className="directory-warning">{detail.exclusion_reason}</p>}
        {detail.admission_state === 'admitted' && detail.position && <PositionPanel key={`${detail.community_id}-${detail.position.revision}`} position={detail.position} busy={busy || !!jobs.amap?.running} query={() => void positionAction('query')} confirm={body => void positionAction('confirm', body)} />}
        <button className="btn btn-secondary" disabled={busy} onClick={() => void action(`/directory/workflow/catalog/${encodeURIComponent(detail.community_id)}/retry`, 'POST')}>更新透明售房网资料</button>
        {detail.sources?.map(s => <DirectorySourceCard key={s.id} item={s} />)}
        {detail.admission && <details><summary>历史审核记录</summary><p>{detail.admission.decision_kind === 'migration' ? '历史资料初始化' : detail.admission.decision_kind === 'manual' ? '历史人工决定' : '历史收录决定'}</p><p>{detail.admission.reason}</p><p className="directory-muted">当前名单按透明售房网有效资料计算，上述内容仅为历史记录。</p></details>}
        <details><summary>历史操作</summary>{detail.events?.map(e => <p key={e.seq}>{e.created_at.slice(0, 19)} · {e.action}{e.payload.reason ? ` · ${e.payload.reason}` : ''}</p>)}</details></>}
    </aside>}</div>
    {summary?.active && <details className="review-rental"><summary>租金来源待处理</summary><p className="directory-muted">查不到或有多个候选的房天下来源在这里处理，不影响住宅名单。</p><RentalAssociationReview onChanged={changed} /></details>}
  </section>;
}
