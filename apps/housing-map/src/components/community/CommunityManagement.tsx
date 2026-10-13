'use client';

import { useEffect, useRef, useState } from 'react';

type Source = { id: string; source: string; source_kind: string; source_id: string; name: string;
  address?: string; district?: string; community_id?: string; status: string; method?: string;
  evidence?: string[]; source_url?: string; sample_count?: number; candidates?: Community[]; possible_deleted?: string[] };
type Community = { community_id: string; community_name: string; aliases?: string[]; district?: string;
  address?: string; deleted?: boolean; sources?: Source[]; eligible?: boolean; evidence?: string[];
  longitude?: number; latitude?: number; has_boundary?: boolean;
  events?: { seq: number; action: string; created_at: string; payload: { reason?: string } }[] };
type Report = { running: boolean; phase: string; source?: string; new?: number; existing?: number;
  matched?: number; pending?: number; ignored?: number; errors?: { source: string; message: string }[];
  truncated?: { source: string; message: string }[] };
const labels: Record<string, string> = { tmsf: '透明售房网', fang: '房天下', amap: '高德', laipai: '来拍 ya' };
const phaseLabels: Record<string, string> = { running: '正在采集', succeeded: '采集结束', partial_failed: '部分完成',
  failed: '采集失败', cancelled: '已取消', interrupted: '服务重启，采集中断', cancelling: '正在取消' };
const root = '/api/map/directory';

async function request<T>(path: string, method = 'GET', body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch(root + path, { method, signal,
    ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
  const payload = await response.json();
  if (!response.ok || !payload.success) throw new Error(typeof payload.detail === 'string' ? payload.detail : '小区数据操作失败，请重试');
  return payload.data;
}
export function safeDirectoryLink(url?: string): string | undefined {
  try { const u = new URL(url || ''); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? url : undefined; }
  catch { return undefined; }
}
export function DirectorySourceCard({ item, children }: { item: Source; children?: React.ReactNode }) {
  const link = safeDirectoryLink(item.source_url);
  return <article className="directory-source-card">
    <div className="directory-source-heading"><span className="directory-badge">{labels[item.source] || item.source}</span>
      <strong>{item.name}</strong><span className="directory-muted">{item.status === 'ignored' ? '已删除' : item.status === 'pending' ? '待关联' : item.method === 'auto' ? '自动关联' : '人工关联'}</span></div>
    <p className="directory-muted">{item.source_kind} · ID {item.source_id}</p>
    <p>{item.address || '地址尚未取得'} · {item.district || '区域未知'}</p>
    {item.evidence?.map((e, i) => <p className="directory-evidence" key={i}>{e}</p>)}
    {link && <a href={link} target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a>}
    {children}
  </article>;
}

export default function CommunityManagement({ onChanged }: { onChanged: () => void }) {
  const [mode, setMode] = useState<'communities' | 'sources'>('communities');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('active');
  const [source, setSource] = useState('');
  const [districtFilter, setDistrictFilter] = useState('滨江');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<(Community | Source)[]>([]);
  const [total, setTotal] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<{ kind: 'communities' | 'sources'; id: string } | null>(null);
  const [detail, setDetail] = useState<Community | Source | null>(null);
  const [name, setName] = useState('');
  const [aliases, setAliases] = useState('');
  const [address, setAddress] = useState('');
  const [district, setDistrict] = useState('滨江');
  const [targetQuery, setTargetQuery] = useState('');
  const [targets, setTargets] = useState<Community[]>([]);
  const [targetId, setTargetId] = useState('');
  const [newForm, setNewForm] = useState(false);
  const [confirm, setConfirm] = useState<{ path: string; method: string; body?: object; text: string } | null>(null);
  const confirmationDialog = useRef<HTMLDialogElement>(null);
  const [report, setReport] = useState<Report | null>(null);
  const previouslyRunning = useRef(false);
  const [collectionSources, setCollectionSources] = useState(Object.keys(labels));
  const [maxPages, setMaxPages] = useState(10);
  useEffect(() => { if (confirm) confirmationDialog.current?.showModal(); }, [confirm]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError('');
      const params = new URLSearchParams({ q, page: String(page), page_size: '30', district: districtFilter });
      if (mode === 'communities') params.set('deleted', String(status === 'deleted'));
      else { params.set('status', status === 'deleted' ? 'ignored' : status === 'active' ? '' : status); params.set('source', source); }
      request<{ items: (Community | Source)[]; total: number }>(`/${mode}?${params}`, 'GET', undefined, controller.signal)
        .then(data => { if (!controller.signal.aborted) { setRows(data.items); setTotal(data.total); } })
        .catch(e => { if (!controller.signal.aborted) setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [mode, q, status, source, districtFilter, page, revision]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    request<Community | Source>(`/${selected.kind}/${encodeURIComponent(selected.id)}`, 'GET', undefined, controller.signal)
      .then(d => { if (controller.signal.aborted) return; setDetail(d); setName('community_name' in d ? d.community_name : d.name);
        setAliases('community_name' in d ? (d.aliases || []).join('、') : ''); setAddress(d.address || ''); setDistrict(d.district || '滨江'); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [selected, revision]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      request<{ items: Community[] }>(`/communities?q=${encodeURIComponent(targetQuery)}&page_size=100`, 'GET', undefined, controller.signal)
        .then(data => { if (!controller.signal.aborted) setTargets(data.items); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [selected, targetQuery, revision]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<Report | null>('/collection', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (previouslyRunning.current && !next?.running) { setRevision(v => v + 1); onChanged(); }
        previouslyRunning.current = !!next?.running;
        setReport(next);
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '进度加载失败'); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2500);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [onChanged]);

  async function act(path: string, method: string, body?: object) {
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await request<{ matched?: number } | null>(path, method, body);
      setRevision(v => v + 1); onChanged(); setConfirm(null);
      setNotice(path === '/auto-associate' ? `自动关联完成：${data?.matched || 0} 条，其余保留待确认。` : '操作已保存。');
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError('');
    try {
      const path = selected?.kind === 'sources' ? `/sources/${selected.id}/create-community` : '/communities';
      const c = await request<Community>(path, 'POST', { name, aliases: aliases.split(/[、,，]/).filter(Boolean), district, address });
      setNewForm(false); setSelected({ kind: 'communities', id: c.community_id }); setDetail(null); setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '创建失败'); }
    finally { setBusy(false); }
  }
  function choose(kind: 'communities' | 'sources', id: string) {
    setSelected({ kind, id }); setDetail(null); setTargetId(''); setTargetQuery(''); setNewForm(false); setConfirm(null);
  }
  const c = detail && 'community_name' in detail ? detail : null;
  const s = detail && 'source_id' in detail ? detail : null;
  const inputForm = <div className="directory-edit-grid">
    <label>标准小区名称<input value={name} onChange={e => setName(e.target.value)} maxLength={100} /></label>
    <label>别名（顿号分隔）<input value={aliases} onChange={e => setAliases(e.target.value)} /></label>
    <label>区域<input value={district} onChange={e => setDistrict(e.target.value)} maxLength={30} /></label>
    <label>地址<input value={address} onChange={e => setAddress(e.target.value)} maxLength={300} /></label>
  </div>;

  return <section className="directory-page">
    <header className="directory-header"><div><p className="directory-kicker">COMMUNITY DIRECTORY</p><h2>小区数据管理</h2>
      <p className="directory-muted">四个来源，一份目录。保留原始名称，集中处理关联与删除。</p></div>
      <button className="btn btn-secondary" disabled={busy} onClick={() => { setSelected(null); setDetail(null); setName(''); setAliases(''); setAddress(''); setDistrict('滨江'); setNewForm(true); }}>新增小区</button></header>
    <div className="directory-collection">
      <div className="directory-actions">{Object.entries(labels).map(([key, label]) => <label key={key}><input type="checkbox" checked={collectionSources.includes(key)} onChange={e => setCollectionSources(v => e.target.checked ? [...v, key] : v.filter(k => k !== key))} />{label}</label>)}
        <label>每来源最多页数<input type="number" min={1} max={100} value={maxPages} onChange={e => setMaxPages(Number(e.target.value))} /></label>
        <button className="btn btn-primary" disabled={busy || report?.running || !collectionSources.length || maxPages < 1 || maxPages > 100} onClick={() => void act('/collection', 'POST', { sources: collectionSources, max_pages: maxPages })}>采集名称</button>
        {report?.running && <button className="btn btn-secondary" onClick={() => void act('/collection', 'DELETE')}>取消采集</button>}
        <button className="btn btn-secondary" disabled={busy} onClick={() => void act('/auto-associate', 'POST')}>运行自动关联</button></div>
      <p className="directory-muted">名称采集范围：滨江区；列表分页可能截断。删除的小区及已关联来源会跳过后续详情采集。</p>
      {report && <div role="status"><strong>{phaseLabels[report.phase] || report.phase}{report.source ? ` · ${labels[report.source]}` : ''}</strong>
        <p>新发现 {report.new || 0} · 已存在 {report.existing || 0} · 已关联 {report.matched || 0} · 待确认 {report.pending || 0} · 已跳过 {report.ignored || 0}</p>
        {[...(report.errors || []), ...(report.truncated || [])].map((item, i) => <p className="directory-warning" key={i}>{labels[item.source]}：{item.message}</p>)}</div>}
    </div>
    {error && <p role="alert" className="directory-warning">{error} <button className="btn btn-secondary" onClick={() => setRevision(v => v + 1)}>重试</button></p>}
    {notice && <p role="status">{notice}</p>}
    <div className="directory-toolbar"><div className="directory-switch"><button aria-pressed={mode === 'communities'} onClick={() => { setMode('communities'); setPage(1); setStatus('active'); }}>统一小区</button><button aria-pressed={mode === 'sources'} onClick={() => { setMode('sources'); setPage(1); setStatus('pending'); }}>来源名称 / 待关联</button></div>
      <input aria-label="搜索小区名称" placeholder="搜索标准名、别名或来源名称" value={q} onChange={e => { setQ(e.target.value); setPage(1); }} />
      <select aria-label="目录区域" value={districtFilter} onChange={e => { setDistrictFilter(e.target.value); setPage(1); }}><option value="滨江">滨江区</option><option value="萧山">萧山接壤目录</option><option value="">全部区域</option></select>
      <select aria-label="记录状态" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="active">{mode === 'communities' ? '有效小区' : '所有来源'}</option>{mode === 'sources' && <><option value="pending">待关联</option><option value="matched">已关联</option></>}<option value="deleted">已删除</option></select>
      {mode === 'sources' && <select aria-label="数据来源" value={source} onChange={e => { setSource(e.target.value); setPage(1); }}><option value="">全部来源</option>{Object.entries(labels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</div>
    <div className="directory-workspace"><div className="directory-list-panel">
      <p className="directory-muted">共 {total} 条 · 第 {page} 页</p>
      {loading ? <p role="status">正在加载目录…</p> : <><div className="directory-table-wrap"><table><thead><tr><th>小区名称</th><th>区域 / 地址</th><th>来源与关联</th><th>操作</th></tr></thead><tbody>
        {rows.map(row => { const master = 'community_name' in row; const id = master ? row.community_id : row.id;
          return <tr key={id} className={selected?.id === id ? 'selected' : ''}><td><strong>{master ? row.community_name : row.name}</strong><small>{master ? (row.aliases || []).join(' / ') : `${labels[row.source]} · ${row.source_id}`}</small></td>
            <td>{row.district || '未知'}<small>{row.address || '地址待补充'}</small></td><td>{master ? (row.sources || []).map(r => <span className="directory-badge" key={r.id}>{labels[r.source]}</span>) : row.status === 'pending' ? '待关联' : row.status === 'ignored' ? '已删除' : row.method === 'auto' ? '自动关联' : '人工关联'}</td>
            <td><button className="btn btn-secondary" onClick={() => choose(master ? 'communities' : 'sources', id)}>管理</button></td></tr>; })}
      </tbody></table></div>{!rows.length && <p className="directory-empty">没有符合条件的记录。</p>}</>}
      <div className="directory-actions"><button className="btn btn-secondary" disabled={page === 1 || loading} onClick={() => setPage(v => v - 1)}>上一页</button><button className="btn btn-secondary" disabled={page * 30 >= total || loading} onClick={() => setPage(v => v + 1)}>下一页</button></div>
    </div>
    {(selected || newForm) && <aside className="directory-detail"><div className="directory-source-heading"><h3>{c?.community_name || s?.name || (newForm ? '新增小区' : '加载详情…')}</h3><button className="btn btn-secondary" onClick={() => { setSelected(null); setDetail(null); setNewForm(false); }}>关闭</button></div>
      {c && !c.deleted && <>{inputForm}<button className="btn btn-primary" disabled={busy} onClick={() => void act(`/communities/${c.community_id}`, 'PUT', { name, aliases: aliases.split(/[、,，]/).filter(Boolean), address, district })}>保存名称与别名</button>
        <p className="directory-muted">中心点：{c.longitude && c.latitude ? `${c.longitude}, ${c.latitude}` : '待补充'} · 边界：{c.has_boundary ? '已关联' : '未关联'}</p></>}
      {c?.sources?.map(r => <DirectorySourceCard key={r.id} item={r}>{!c.deleted && <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirm({ path: `/sources/${r.id}/associate`, method: 'DELETE', text: `解除“${r.name}”与当前小区的关联？解除后原来源租金或法拍不再归到这个小区。` })}>解除关联</button>}</DirectorySourceCard>)}
      {s && <DirectorySourceCard item={s}><p>已保存租房样本 {s.sample_count || 0} 条</p>{s.status === 'matched' && <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirm({ path: `/sources/${s.id}/associate`, method: 'DELETE', text: '解除当前关联？已有数据将按新的关联关系展示。' })}>解除当前关联</button>}</DirectorySourceCard>}
      {s?.status === 'pending' && <>{!!s.possible_deleted?.length && <p className="directory-warning">与已删除小区同名：{s.possible_deleted.join('、')}。请核对是否来源换了 ID，避免重复建立。</p>}<h4>关联候选</h4>{s.candidates?.length ? s.candidates.map(candidate => <div className="directory-candidate" key={candidate.community_id}><strong>{candidate.community_name}</strong><p>{candidate.address || '地址未知'}</p>{candidate.evidence?.map(e => <small key={e}>{e}</small>)}<div className="directory-actions"><button className="btn btn-primary" disabled={busy} onClick={() => setConfirm({ path: `/sources/${s.id}/associate`, method: 'POST', body: { community_id: candidate.community_id }, text: `确认“${s.name}”与“${candidate.community_name}”是同一小区、同一分期？` })}>确认关联</button><button className="btn btn-secondary" disabled={busy} onClick={() => void act(`/sources/${s.id}/associate?community_id=${candidate.community_id}`, 'DELETE')}>不是此小区</button></div></div>) : <p className="directory-muted">没有名称候选，可搜索已有目录或建立新小区。</p>}</>}
      {((s && s.status !== 'ignored') || (c && !c.deleted)) && <div className="directory-linker"><h4>{s ? '手动选择小区' : '合并到已有小区'}</h4>
        <input aria-label="搜索关联目标" placeholder="搜索目标小区" value={targetQuery} onChange={e => { setTargetQuery(e.target.value); setTargetId(''); }} />
        <select aria-label="目标小区" value={targetId} onChange={e => setTargetId(e.target.value)}><option value="">选择目标小区</option>{targets.filter(t => t.community_id !== c?.community_id).map(t => <option key={t.community_id} value={t.community_id}>{t.community_name} · {t.district} · {t.address}</option>)}</select>
        <button className="btn btn-secondary" disabled={busy || !targetId} onClick={() => setConfirm({ path: s ? `/sources/${s.id}/associate` : `/communities/${c!.community_id}/merge`, method: 'POST', body: { community_id: targetId }, text: s ? '确认关联到选定小区？请核对地址和分期。' : '确认合并？来源与历史归到目标小区，原名称保留为别名。' })}>{s ? '关联所选小区' : '合并至所选小区'}</button>
        {s?.status === 'pending' && <button className="btn btn-secondary" disabled={busy} onClick={() => setNewForm(v => !v)}>作为新小区建立</button>}</div>}
      {newForm && <>{inputForm}<button className="btn btn-primary" disabled={busy || !name.trim()} onClick={() => void create()}>创建{s ? '并关联' : ''}</button></>}
      {(c || s) && <div className="directory-danger">{c?.deleted || s?.status === 'ignored' ? <button className="btn btn-secondary" disabled={busy} onClick={() => { if (s?.community_id) choose('communities', s.community_id); else void act(c ? `/communities/${c.community_id}/restore` : `/sources/${s!.id}/restore`, 'POST'); }}>恢复{c || s?.community_id ? '整个小区' : '来源候选'}</button> : <><p>删除会排除整个小区及所有已关联来源，后续采集跳过；历史保留。</p><button className="btn btn-secondary" disabled={busy} onClick={() => setConfirm({ path: c ? `/communities/${c.community_id}` : `/sources/${s!.id}`, method: 'DELETE', text: s && !s.community_id ? '此来源尚未关联小区，删除会记住该来源身份，下次采集跳过。' : '确认删除整个小区及所有已关联来源？将停止详情采集和业务展示，历史保留且可恢复。' })}>删除{c || s?.community_id ? '整个小区' : '未关联候选'}</button></>}</div>}
      {c?.events && <details><summary>操作记录（最近 {c.events.length} 条）</summary>{c.events.map(e => <p className="directory-muted" key={e.seq}>{e.created_at.slice(0, 19).replace('T', ' ')} UTC · {e.action}{e.payload.reason ? ` · ${e.payload.reason}` : ''}</p>)}</details>}
    </aside>}</div>
    {confirm && <dialog ref={confirmationDialog} className="directory-confirm" aria-label="确认目录操作" onCancel={() => setConfirm(null)}><p>{confirm.text}</p><div className="directory-actions"><button autoFocus className="btn btn-primary" disabled={busy} onClick={() => void act(confirm.path, confirm.method, confirm.body)}>确认操作</button><button className="btn btn-secondary" disabled={busy} onClick={() => setConfirm(null)}>返回核对</button></div></dialog>}
  </section>;
}
