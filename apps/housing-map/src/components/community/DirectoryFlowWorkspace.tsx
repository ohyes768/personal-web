'use client';

import { useEffect, useRef, useState } from 'react';
import { Community, Source, DirectorySourceCard, marketLabels, mapLabels, safeDirectoryLink } from './DirectoryCards';
import PositionPanel, { Position, PositionBadge, positionLabels, positionBucketLabels } from './PositionPanel';
import UseReviewPanel, { UseReview, UseReviewBadge, useReviewFilterLabels, formatUseReviewMessage } from './UseReviewPanel';
import RentalAssociationReview from '../rental/RentalAssociationReview';
import DirectoryDialog from './DirectoryDialog';
import { rentalRefreshDiagnostics } from '../../lib/rental-dashboard';
import type { RentalRequestDiagnostics } from '../../lib/rental-types';
import { AuctionCoverage, RentalCoverage, CatalogAuctionRecords, CatalogRentalDetails, rentalCoverageLabels, type CatalogCoverage, type CatalogAuctionRecord } from './CatalogCoverage';

type CatalogRow = Community & { property_types?: string[]; position?: Position; use_review?: UseReview;
  collection_pipeline_version?: string; workflow_state?: 'pending' | 'admitted' | 'excluded';
  qualification: string; facts_state: string; exclusion_reason: string;
  source_record_id?: string; geographic_address?: string; coordinate_evidence?: { source_id?: string; captured_at?: string };
  coverage?: CatalogCoverage; auction_records?: CatalogAuctionRecord[] };
type Auction = Source & { revision: string; skipped: boolean; candidates: Community[]; reason: string;
  auction_ids?: string[]; rounds?: { auction_id: string; title?: string; source_url?: string; round?: number }[] };
type Summary = { active: boolean; admitted: number; excluded: number; auction_pending: number; pipeline?: boolean; pending?: number };

export function catalogScope(mode: string, pipeline = false) {
  return { state: mode === 'pending' ? 'excluded' : mode,
    workflow: pipeline && (mode === 'pending' || mode === 'excluded') ? mode : '' };
}

export function CatalogTabs({ summary, mode, onChange }: { summary: Summary | null; mode: string; onChange: (mode: string) => void }) {
  const tabs = [['admitted', '已收录', summary?.admitted],
    ...(summary?.pipeline ? [['pending', '待处理', summary.pending]] : []),
    ['excluded', '不收录', summary?.pipeline ? Math.max(0, summary.excluded - (summary.pending || 0)) : summary?.excluded],
    ['auctions', '法拍待关联', summary?.auction_pending], ['rental', '租金来源', null]];
  return <div className="review-tabs">{tabs.map(([key, label, count]) =>
    <button key={key} aria-pressed={mode === key} onClick={() => onChange(String(key))}>{count == null ? label : `${label}（${count}）`}</button>)}</div>;
}
type Page<T> = { items: T[]; total: number; page: number; property_types?: string[] };
type Job = RentalRequestDiagnostics & { running: boolean; phase: string; finished_at?: string; started_at?: string; processed?: number; total?: number;
  matched?: number; new?: number; existing?: number; updated?: number; skipped?: number; review?: number; not_found?: number;
  failed?: number; conflict?: number; uncertain?: number; requests?: number; skipped_by_state?: Record<string, number>; error?: string;
  retryable?: number; mode?: 'all' | 'retry_failed';
  stage?: string; association?: { checked?: number; matched?: number; pending?: number; missing?: number; failed?: number; deferred?: number }; errors?: { message: string; name?: string; state?: string; reason?: string }[]; truncated?: { message: string; state?: string; reason?: string }[] };
type IncomingJob = Omit<Job, 'errors'> & { total_communities?: number; processed_communities?: number;
  errors?: Job['errors'] | { items?: { message: string }[]; total?: number } };
export function normalizeCollectionJob(value: IncomingJob | null): Job | null {
  if (!value) return null;
  return { ...value, total: value.total ?? value.total_communities, processed: value.processed ?? value.processed_communities,
    errors: Array.isArray(value.errors) ? value.errors : value.errors?.items || [] };
}
const tasks = [
  { id: 'tmsf', label: '住宅名称采集', short: '透明售房网', stop: '停止采集', path: '/directory/collection', hint: '更新全部资料会重新扫描名单、更新用途和挂牌数量；重试失败项仅补采获取失败的楼盘资料，保留成功项，自动分类收录。', body: { sources: ['tmsf'] } },
  { id: 'amap', label: '补全高德定位', short: '高德定位', stop: '停止补全定位', path: '/directory/workflow/positions', hint: '仅已收录住宅；批量补待补全和失败项，保留人工结果' },
  { id: 'use', label: '核对住宅用途', short: '用途核对', stop: '停止用途核对', path: '/directory/workflow/use-reviews', hint: '核对用途缺失、其他、冲突、公寓商住等需核实项目及已定位住宅；已有人工决定、明确非住宅和区域异常项不重复查询，发现冲突后由你确认。' },
  { id: 'rent', label: '采集租金', short: '租金', stop: '停止采集租金', path: '/rentals/refresh', hint: '仅已收录住宅；复用关联，更新幸福里或房天下租金' },
  { id: 'auction', label: '采集法拍', short: '法拍', stop: '停止采集法拍', path: '/auctions/refresh', hint: '采集滨江法拍，匹配住宅，未匹配进入待关联' },
];
const restPhases = ['idle', 'succeeded', 'done'];
const stageLabels: Record<string, string> = { checking: '检查租金来源', discovering: '查找租金来源', crawling: '采集租金房源',
  publishing: '发布租金统计', names: '更新小区名录', property_types: '补充用途资料' };
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

function taskCounts(t: (typeof tasks)[number], job: Job | null): string {
  return [job?.stage && stageLabels[job.stage],
    job?.processed !== undefined && `已处理 ${job.processed}${job.total !== undefined ? ` / ${job.total}` : ''}`,
    job?.new !== undefined && `新来源 ${job.new} · 已有 ${job.existing || 0}`,
    job?.updated !== undefined && job.review !== undefined &&
      `补全 ${job.updated || 0} · 待人工确认 ${job.review} · 未找到主体地点 ${job.not_found || 0}${job.failed ? ` · 查询失败 ${job.failed}` : ''}`,
    job?.updated !== undefined && job.review === undefined && job.conflict === undefined && `补全 ${job.updated} · 跳过 ${job.skipped || 0}`,
    job?.conflict !== undefined &&
      `已完成用途核对 ${job.updated || 0} · 用途冲突，待人工确认 ${job.conflict} · 未找到高德地点 ${job.not_found || 0}${job.uncertain ? ` · 高德地点匹配不明确 ${job.uncertain}` : ''}${job.error ? ` · 查询失败 ${job.error}` : ''} · 跳过 ${job.skipped || 0}`,
    job?.matched !== undefined && t.id === 'auction' && `本次法拍 ${job.matched} 条`].filter(Boolean).join(' · ');
}
function taskStateOf(t: (typeof tasks)[number], jobs: Record<string, Job | null>, errors: Record<string, string>): 'running' | 'failed' | 'info' {
  const job = jobs[t.id];
  return job?.running ? 'running' : (errors[t.id] || job?.error) ? 'failed' : 'info';
}
function taskRelevant(t: (typeof tasks)[number], jobs: Record<string, Job | null>, errors: Record<string, string>): boolean {
  const job = jobs[t.id];
  return !!errors[t.id] || !!job?.running || !!job?.error ||
    (!!job && (t.id === 'amap' ? job.processed !== undefined : !restPhases.includes(job.phase)));
}

/** 采集任务弹层：触发/停止/完整进度都收在弹层里；运行中另有单行状态条常驻（CollectionControls 返回的 summary）。 */
export function CollectionControls({ active, jobs, errors, busy, action, open = false, onOpenChange = () => {}, pipeline = false }: {
  pipeline?: boolean;
  active: boolean; jobs: Record<string, Job | null>; errors: Record<string, string>; busy: boolean;
  action: (path: string, method: string, body?: object) => void; open?: boolean; onOpenChange?: (open: boolean) => void }) {
  const availableTasks = tasks.filter(t => !pipeline || t.id !== 'use').map(t => pipeline && t.id === 'amap'
    ? { ...t, label: '匹配楼盘地点与类型', hint: '候选楼盘先确认主体地点，同时保存坐标与类型，再自动分类；多个主体由你选择。' }
    : pipeline && t.id === 'tmsf' ? { ...t, label: '采集楼盘名单与资料' } : t);
  const relevant = availableTasks.filter(t => taskRelevant(t, jobs, errors));
  const anyRunning = relevant.some(t => taskStateOf(t, jobs, errors) === 'running');
  const anyFailed = relevant.some(t => taskStateOf(t, jobs, errors) === 'failed');
  return <>
    {relevant.length > 0 && <button type="button" className="directory-task-summary"
      data-state={anyFailed ? 'failed' : anyRunning ? 'running' : 'info'}
      aria-haspopup="dialog" onClick={() => onOpenChange(true)}>
      <span className="directory-task-dot" aria-hidden="true" />
      {relevant.map(t => {
        const job = jobs[t.id];
        const problem = errors[t.id] || job?.error || '';
        const message = job ? [job.mode === 'retry_failed' && '重试失败项', phases[job.phase] || job.phase, taskCounts(t, job)].filter(Boolean).join(' · ') : '';
        return <span key={t.id}><strong>{t.short}</strong> {problem || message}</span>;
      })}
      <span className="directory-task-more">详情</span>
    </button>}
    {open && <DirectoryDialog title="采集任务" onClose={() => onOpenChange(false)}>
      {!active && <p className="directory-warning">名单流程尚未启用，采集暂不可用。</p>}
      {availableTasks.map(t => {
        const job = jobs[t.id];
        const running = !!job?.running;
        const state = taskStateOf(t, jobs, errors);
        const problem = errors[t.id] || job?.error || '';
        const message = job ? [job.mode === 'retry_failed' && '重试失败项', phases[job.phase] || job.phase, taskCounts(t, job)].filter(Boolean).join(' · ') : '';
        const lastRun = job?.finished_at ? ` · 上次结束：${job.finished_at.slice(0, 19).replace('T', ' ')}（UTC）` : '';
        const issues = [...(job?.errors || []), ...(job?.truncated || [])];
        const isReview = (e: (typeof issues)[number]) => t.id === 'amap' && e.state === 'review' && e.reason !== 'results_incomplete';
        const isMissing = (e: (typeof issues)[number]) => t.id === 'amap' && e.state === 'not_found';
        const reviewIssues = issues.filter(isReview);
        const missingIssues = issues.filter(isMissing);
        const retryIssues = issues.filter(e => !isReview(e) && !isMissing(e));
        return <div key={t.id} className="directory-task-row" data-state={state}>
          <div className="directory-task-row-head">
            <span className="directory-task-dot" aria-hidden="true" />
            <strong>{t.label}</strong>
            <div className="directory-task-actions"><button className={`btn ${running ? 'btn-secondary' : 'btn-primary'}`} disabled={busy || (!active && !running)}
              onClick={() => (running ? action(t.path, 'DELETE') : action(t.path, 'POST', t.body))}>
              {running ? t.stop : t.id === 'tmsf' ? '更新全部资料' : '开始'}</button>
            {t.id === 'tmsf' && <button className="btn btn-secondary" disabled={busy || !active || running || !job?.retryable}
              onClick={() => action(t.path, 'POST', { ...t.body, mode: 'retry_failed' })}>
              重试失败项（{job?.retryable || 0}）</button>}</div>
          </div>
          <p className="directory-task-hint">{t.hint}<span className="directory-task-lastrun">{lastRun}</span></p>
          {(problem || message) && <p className="directory-task-line" data-state={state}>
            {problem ? <span role="alert">{problem}</span> : <span role="status">{message}</span>}
          </p>}
          {job?.association && <p className="directory-task-sub">已检查 {job.association.checked || 0} · 已关联 {job.association.matched || 0} · 待选择 {job.association.pending || 0} · 未找到 {job.association.missing || 0} · 查询失败 {job.association.failed || 0} · 未查询 {job.association.deferred || 0}</p>}
          {t.id === 'rent' && rentalRefreshDiagnostics(job) && <p className="directory-task-sub">{rentalRefreshDiagnostics(job)}</p>}
          {t.id === 'amap' && !!job?.skipped_by_state && Object.keys(job.skipped_by_state).length > 0 &&
            <p className="directory-task-sub">未参与本轮 {job.skipped || 0}（{Object.entries(job.skipped_by_state).map(([k, v]) => `${positionLabels[k] || k} ${v}`).join(' · ')}）</p>}
          {reviewIssues.length > 0 && <details className="directory-task-sub"><summary>待人工确认地点（{reviewIssues.length}）</summary>
            <p>请在列表中查看地点与类型，核对后选择主体；待确认是正常审核步骤。</p>
            {reviewIssues.map((e, i) => <p key={i}>{'name' in e && e.name ? `${e.name}：` : ''}{e.message.startsWith('未找到唯一可靠位置：') ? '候选地点需人工核对，请查看资料并选择主体' : e.message}</p>)}</details>}
          {missingIssues.length > 0 && <details className="directory-task-sub"><summary>未找到主体地点（{missingIssues.length}）</summary>
            <p>可补充别名后重新查询，或查看相关地点类型；未找到不代表非住宅。</p>
            {missingIssues.map((e, i) => <p key={i}>{'name' in e && e.name ? `${e.name}：` : ''}{e.message}</p>)}</details>}
          {retryIssues.length > 0 && <details className="directory-task-sub"><summary>{t.id === 'amap' ? '查询未完成（可重试）' : '本轮未完成事项（可重试）'}</summary>
            {retryIssues.map((e, i) => <p key={i}>{'name' in e && e.name ? `${e.name}：` : ''}{t.id === 'use' ? formatUseReviewMessage(e.message) : e.message}</p>)}</details>}
        </div>;
      })}
    </DirectoryDialog>}
  </>;
}

/** 标题行右端的采集任务入口：齿轮空闲，运行/失败时以状态点替换并高亮。 */
export function CollectionTasksButton({ jobs, errors, onOpen }: {
  jobs: Record<string, Job | null>; errors: Record<string, string>; onOpen: () => void }) {
  const running = tasks.some(t => jobs[t.id]?.running);
  const failed = tasks.some(t => errors[t.id] || jobs[t.id]?.error);
  const state = running ? 'running' : failed ? 'failed' : 'idle';
  return <button type="button" className="btn btn-secondary directory-task-gear" data-state={state} aria-haspopup="dialog"
    title={running ? '有采集任务运行中' : failed ? '有采集任务失败' : '采集任务'} onClick={onOpen}>
    {state === 'idle' ? <span aria-hidden="true">⚙️</span> : <span className="directory-task-dot" aria-hidden="true" />}采集任务
  </button>;
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

export function pipelineStageLabel(row: Pick<CatalogRow, 'workflow_state' | 'qualification'>): string {
  if (row.workflow_state === 'admitted') return '已收录';
  if (row.workflow_state === 'excluded') return '明确不收录';
  return ({ position_pending: '待匹配地点', position_review: '待确认地点', position_type_missing: '待补主体类型',
    use_conflict: '待确认用途', use_uncertain: '待确认用途', type_uncertain: '待确认用途',
    type_missing: '待补用途资料', type_conflict: '待核实用途', region_conflict: '待核实区域' } as Record<string, string>)[row.qualification] || '待补资料';
}

export function catalogCanExclude(row?: Pick<CatalogRow, 'admission_state' | 'workflow_state' | 'qualification' | 'source_record_id' | 'admission'> | null): boolean {
  return !!row && !row.source_record_id && !!row.admission?.revision && row.qualification !== 'manual_exclusion';
}

function CatalogAmapType({ position }: { position?: Position }) {
  const selected = position?.selected;
  const candidates = position?.candidates || [];
  const references = position?.reference_candidates || [];
  const types = (points: typeof candidates) => Array.from(new Set(points.map(p => p.poi_type || p.poi_typecode || '类型缺失'))).join(' / ');
  if (selected) return <span>{selected.poi_type || selected.poi_typecode || '类型缺失'}</span>;
  if (candidates.length || references.length) return <>
    {!!candidates.length && <div>{types(candidates)}<small className="directory-muted">候选主体 · 待确认</small></div>}
    {!!references.length && <div>{types(references)}<small className="directory-muted">相关地点 · 仅供参考</small></div>}
  </>;
  const empty = position?.state === 'error' ? '查询失败' : position?.state === 'not_found' ? '未找到相关地点'
    : position?.state === 'review' ? '待确认地点，类型缺失' : position?.checked_at ? '未获取类型' : '未查询';
  return <span className="directory-muted">{empty}</span>;
}

export function CatalogTable({ items, excluded, pending = false, select, retry, busy, position, exclude }: { items: CatalogRow[]; excluded: boolean; pending?: boolean;
  select: (row: CatalogRow) => void; retry: (row: CatalogRow) => void; busy: boolean; position?: (row: CatalogRow) => void; exclude?: (row: CatalogRow) => void; }) {
  return <div className="directory-table-wrap"><table className={`review-table catalog-table ${excluded ? 'catalog-excluded' : 'catalog-admitted'}${pending ? ' catalog-pending' : ''}`}><thead><tr>
    <th>{excluded ? '小区名称' : '小区 / 地址'}</th>{excluded && <th>区域 / 实际地址</th>}<th>{excluded ? '房屋用途' : '新房 / 二手房'}</th>
    <th>高德类型</th>{excluded && <th>住宅用途核对</th>}<th>{excluded ? pending ? '待处理原因 / 资料状态' : '不收录原因 / 资料状态' : '高德定位'}</th>{!excluded && <><th>法拍</th><th>租金</th></>}{pending && <th>收录决定</th>}<th>操作</th>
  </tr></thead><tbody>{items.map(c => <tr key={c.community_id}>
    <td data-label={excluded ? '小区名称' : '小区 / 地址'}><strong className="catalog-text" title={c.community_name}>{c.community_name}</strong>{!!c.aliases?.length && <small className="catalog-text" title={c.aliases.join(' / ')}>{c.aliases.join(' / ')}</small>}
      {!excluded && <small className="catalog-text directory-muted" title={c.address || '实际地址待补充'}>{c.district || '区域待补'} · {c.address || '实际地址待补充'}</small>}</td>
    {excluded && <td data-label="区域 / 实际地址">{c.district || '区域待补'}<small className="catalog-text" title={c.address || '实际地址待补充'}>{c.address || '实际地址待补充'}</small></td>}
    <td data-label={excluded ? '房屋用途' : '新房 / 二手房'}>{excluded
      ? c.property_types?.join(' / ') || c.effective_property_type || [...new Set(c.sources?.filter(s => s.source === 'tmsf').map(s => s.property_type).filter(Boolean))].join(' / ') || '用途资料缺失'
      : marketLabels[c.market_state || 'unknown'] || marketLabels.unknown}</td>
    <td data-label="高德类型"><CatalogAmapType position={c.position} /></td>
    {excluded && <td data-label="住宅用途核对"><div className="catalog-inline"><UseReviewBadge review={c.use_review} compact />
      {c.collection_pipeline_version && <small className="catalog-text">{pipelineStageLabel(c)}</small>}
      {c.use_review?.auto_skip_reason && <small className="catalog-text directory-muted">{c.use_review.auto_skip_reason}</small>}
      {c.use_review?.re_review && <small className="catalog-text directory-muted">有新证据待复审</small>}</div></td>}
    {excluded && <td data-label={pending ? '待处理原因 / 资料状态' : '不收录原因 / 资料状态'}>{c.exclusion_reason}<small>{c.facts_state === 'incomplete' ? '资料待补，可重新获取' : pending ? '待核对' : '条件不符'}</small></td>}
    {!excluded && <td data-label="高德定位"><div className="catalog-inline"><PositionBadge position={c.position} compact />{c.position?.state === 'review' && <button className="btn btn-secondary" disabled={busy} onClick={() => (position || select)(c)}>确认位置</button>}</div></td>}
    {!excluded && <><td data-label="法拍"><AuctionCoverage value={c.coverage?.auction} onView={() => select(c)} /></td>
      <td data-label="租金"><RentalCoverage value={c.coverage?.rental} /></td></>}
    {pending && <td data-label="收录决定">{catalogCanExclude(c) && exclude ? <button className="btn directory-exclude-action" disabled={busy} onClick={() => exclude(c)}>确认不收录</button> : <span className="directory-muted">需先补齐身份</span>}</td>}
    <td data-label="操作"><div className="catalog-inline catalog-row-actions"><button className="btn btn-secondary" onClick={() => select(c)}>查看资料</button>{excluded && <button className="btn btn-secondary" disabled={busy} onClick={() => retry(c)}>更新资料</button>}</div></td>
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
    <p className="directory-muted">这里只建立法拍关联；找不到目标时可先跳过，不会新增住宅。绑定后可在已收录小区的资料弹框中解除，解除后会回到待关联列表重新核对。</p>
    {error && <p role="alert">{error}</p>}
    <div className="directory-actions"><button className="btn btn-primary" disabled={busy || !target} onClick={() => send('bind')}>确认关联</button>
      <button className="btn btn-secondary" disabled={busy} onClick={() => send(row.skipped ? 'reopen' : 'skip')}>{row.skipped ? '重新处理' : '暂时跳过'}</button></div></>;
}

export default function DirectoryFlowWorkspace({ onChanged, initialSource = '' }: { onChanged: () => void; initialSource?: string }) {
  const [mode, setMode] = useState(initialSource === 'laipai' ? 'auctions' : 'admitted');
  const [q, setQ] = useState(''); const [district, setDistrict] = useState('滨江'); const [page, setPage] = useState(1);
  const [positionFilter, setPositionFilter] = useState('');
  const [marketFilter, setMarketFilter] = useState('');
  const [auctionFilter, setAuctionFilter] = useState('');
  const [rentalFilter, setRentalFilter] = useState('');
  const [propertyFilter, setPropertyFilter] = useState('');
  const [useFilter, setUseFilter] = useState('');
  const [useConfirmOpen, setUseConfirmOpen] = useState(false);
  const [propertyTypes, setPropertyTypes] = useState<string[]>([]);
  const [showSkipped, setShowSkipped] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null); const [items, setItems] = useState<CatalogRow[]>([]);
  const [auctions, setAuctions] = useState<Auction[]>([]); const [total, setTotal] = useState(0);
  const [jobs, setJobs] = useState<Record<string, Job | null>>({}); const [jobErrors, setJobErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [detail, setDetail] = useState<CatalogRow | null>(null); const [auction, setAuction] = useState<Auction | null>(null);
  const detailVersion = useRef(0);
  const finishes = useRef<Record<string, string>>({});
  const optimistic = useRef<string | null>(null);
  const changed = () => { detailVersion.current += 1; setRevision(v => v + 1); setDetail(null); setAuction(null); onChanged(); };
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const counts = await workflowRequest<Summary>(`/directory/workflow/summary?${new URLSearchParams({ q, district })}`, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setSummary(counts);
        if (!counts.active) { setLoading(false); return; }
        if (mode === 'rental') { setLoading(false); return; }
        const path = mode === 'auctions' ? `/directory/workflow/auctions?${new URLSearchParams({ q, page: String(page), include_skipped: String(showSkipped) })}`
          : `/directory/workflow/catalog?${new URLSearchParams({ q, district, ...catalogScope(mode, counts.pipeline), page: String(page), position: mode === 'admitted' || mode === 'pending' ? positionFilter : '', market: mode === 'admitted' ? marketFilter : '', property_type: mode === 'excluded' || mode === 'pending' ? propertyFilter : '', use: useFilter, auction: mode === 'admitted' ? auctionFilter : '', rental: mode === 'admitted' ? rentalFilter : '' })}`;
        const packet = await workflowRequest<Page<CatalogRow> | Page<Auction>>(path, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (page > 1 && (page - 1) * 30 >= packet.total) { setPage(Math.max(1, Math.ceil(packet.total / 30))); return; }
        if (mode === 'auctions') setAuctions((packet as Page<Auction>).items); else setItems((packet as Page<CatalogRow>).items);
        if (mode === 'excluded' || mode === 'pending') setPropertyTypes(packet.property_types || []);
        setTotal(packet.total); setError(''); setLoading(false);
      } catch (e) { if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : '名单加载失败'); setLoading(false); } }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [mode, q, district, page, showSkipped, revision, positionFilter, marketFilter, propertyFilter, auctionFilter, rentalFilter, useFilter]);
  useEffect(() => {
    if (!summary?.active) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await Promise.allSettled(tasks.map(async t => {
        try {
          const next = normalizeCollectionJob(await workflowRequest<IncomingJob | null>(t.path, 'GET', undefined, controller.signal));
          if (controller.signal.aborted) return;
          setJobs(v => optimistic.current === t.id ? v : { ...v, [t.id]: next }); setJobErrors(v => ({ ...v, [t.id]: '' }));
          const mark = next?.finished_at || '';
          if (mark && finishes.current[t.id] !== undefined && finishes.current[t.id] !== mark) {
            setRevision(v => v + 1); onChanged();
            setNotice(`${t.short}：${phases[next?.phase || ''] || '已结束'}`);
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
    const task = tasks.find(t => t.path === path);
    const prev = task ? jobs[task.id] : null;
    if (task && method === 'POST') {
      optimistic.current = task.id;
      setJobs(v => ({ ...v, [task.id]: { ...(prev || { running: false, phase: 'idle' }), running: true, phase: 'running' } }));
    }
    try {
      const outcome = await workflowRequest<{ errors?: string[] } | null>(path, method, body);
      setNotice(outcome?.errors?.length ? `部分资料已保存：${outcome.errors.join('；')}` : path.endsWith('/retry') ? '资料已更新，名单已重新分类。' : '操作已受理，采集结果请查看对应进度。');
      changed();
      if (task) {
        const next = normalizeCollectionJob(await workflowRequest<IncomingJob | null>(path));
        setJobs(v => ({ ...v, [task.id]: next }));
      }
    } catch (e) {
      if (task && method === 'POST') setJobs(v => ({ ...v, [task.id]: prev }));
      setError(e instanceof Error ? e.message : '操作失败'); setRevision(v => v + 1);
    }
    finally { optimistic.current = null; setBusy(false); }
  }
  function changeMode(value: string) { setMode(value); setPage(1); setPositionFilter(''); setUseFilter(''); setPropertyFilter(''); setLoading(true); setDetail(null); setAuction(null); detailVersion.current += 1; }
  async function select(row: CatalogRow) {
    const version = ++detailVersion.current;
    setError(''); setNotice(''); setDetail(row); setAuction(null);
    setUseConfirmOpen(row.qualification === 'use_conflict' || row.qualification === 'use_uncertain');
    try {
      const path = `/directory/workflow/catalog/${encodeURIComponent(row.community_id)}`;
      const value = await workflowRequest<CatalogRow>(path);
      if (value.admission_state === 'admitted' || (value.collection_pipeline_version && !value.source_record_id)) value.position = await workflowRequest<Position>(path + '/position');
      if (detailVersion.current === version) setDetail(value);
    }
    catch (e) { if (detailVersion.current === version) setError(e instanceof Error ? e.message : '详情加载失败'); }
  }
  async function positionAction(body: object) {
    if (!detail) return;
    const cid = detail.community_id; const version = detailVersion.current;
    setBusy(true); setError('');
    try {
      const position = await workflowRequest<Position>(`/directory/workflow/catalog/${encodeURIComponent(cid)}/position/confirm`, 'POST', body);
      const fresh = await workflowRequest<CatalogRow>(`/directory/workflow/catalog/${encodeURIComponent(cid)}`);
      if (detailVersion.current === version) setDetail({ ...fresh, position });
      setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '定位操作失败，请刷新'); }
    finally { setBusy(false); }
  }
  async function refreshDetail() {
    if (!detail || busy) return;
    const version = detailVersion.current;
    const path = `/directory/workflow/catalog/${encodeURIComponent(detail.community_id)}`;
    setBusy(true); setError(''); setNotice('');
    let saved = false;
    try {
      const outcome = await workflowRequest<{ errors?: string[] } | null>(path + '/retry', 'POST');
      saved = true;
      const fresh = await workflowRequest<CatalogRow>(path);
      if (fresh.admission_state === 'admitted' || (fresh.collection_pipeline_version && !fresh.source_record_id)) fresh.position = await workflowRequest<Position>(path + '/position');
      if (detailVersion.current === version) {
        setDetail(fresh);
        setNotice(outcome?.errors?.length ? `部分资料已更新：${outcome.errors.join('；')}` : '资料已更新，名单已重新分类。');
      }
    } catch (e) {
      if (detailVersion.current === version) setError(saved ? '资料已更新，但刷新详情失败，请关闭后重新打开。' : e instanceof Error ? e.message : '更新失败，请重试');
    } finally {
      if (saved) { setRevision(v => v + 1); onChanged(); }
      setBusy(false);
    }
  }
  async function queryDetailPosition() {
    if (!detail || busy) return;
    const version = detailVersion.current;
    const path = `/directory/workflow/catalog/${encodeURIComponent(detail.community_id)}`;
    setBusy(true); setError(''); setNotice('');
    try {
      const position = await workflowRequest<Position & { errors?: string[] }>(path + '/position/query', 'POST');
      const fresh = await workflowRequest<CatalogRow>(path);
      if (detailVersion.current === version) {
        setDetail({ ...fresh, position });
        setNotice(position.errors?.length ? position.errors.join('；') : '地点与类型已保存，收录状态已重新计算。');
      }
      setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '地点匹配失败'); }
    finally { setBusy(false); }
  }
  async function reviewAction(kind: 'recheck' | 'confirm', body?: object) {
    if (!detail) return;
    const cid = detail.community_id; const version = detailVersion.current;
    setBusy(true); setError(''); setNotice('');
    try {
      if (kind === 'recheck') {
        const outcome = await workflowRequest<{ errors?: string[] }>(`/directory/workflow/catalog/${encodeURIComponent(cid)}/use-review`, 'POST');
        setNotice(outcome?.errors?.length ? `查询完成：${outcome.errors.map(formatUseReviewMessage).join('；')}` : '用途核对完成，名单已重新分类。');
      } else {
        await workflowRequest(`/directory/workflow/catalog/${encodeURIComponent(cid)}/use-review/confirm`, 'POST', body);
        setNotice('用途已确认，名单已重新分类。');
        setUseConfirmOpen(false);
      }
      const fresh = await workflowRequest<CatalogRow>(`/directory/workflow/catalog/${encodeURIComponent(cid)}`);
      if (fresh.collection_pipeline_version && !fresh.source_record_id) fresh.position = await workflowRequest<Position>(`/directory/workflow/catalog/${encodeURIComponent(cid)}/position`);
      if (detailVersion.current === version) setDetail(fresh);
      setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '用途操作失败，请刷新'); }
    finally { setBusy(false); }
  }
  async function admissionAction(kind: 'exclude' | 'resume', target = detail) {
    if (!target) return;
    const rev = target.admission?.revision;
    if (!rev) { setError('缺少审核版本，请刷新后重试'); return; }
    setBusy(true); setError('');
    try {
      await workflowRequest(`/directory/workflow/catalog/${encodeURIComponent(target.community_id)}/${kind}`, 'POST', { revision: rev, reason: kind === 'exclude' ? '人工确认不收录' : '' });
      setNotice(kind === 'exclude' ? '已转为不收录，自动流程不会再收录；可在不收录列表恢复。' : '已恢复自动分类，是否符合收录条件由透明售房网资料重新判定。');
      changed();
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败，请刷新'); }
    finally { setBusy(false); }
  }
  async function unlinkAuctionSource(sourceId: string) {
    if (!detail) return;
    const cid = detail.community_id; const version = detailVersion.current;
    setBusy(true); setError('');
    try {
      await workflowRequest(`/directory/sources/${encodeURIComponent(sourceId)}/associate?community_id=${encodeURIComponent(cid)}`, 'DELETE');
      const fresh = await workflowRequest<CatalogRow>(`/directory/workflow/catalog/${encodeURIComponent(cid)}`);
      if (detailVersion.current === version) setDetail(fresh);
      setNotice('已解除法拍关联，该记录回到法拍待关联列表。');
      setRevision(v => v + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '解除失败，请重试'); }
    finally { setBusy(false); }
  }
  const resumeAdmission = !!detail && detail.admission_state !== 'admitted' && !detail.source_record_id && detail.qualification === 'manual_exclusion';
  const canExclude = catalogCanExclude(detail);
  return <section className="directory-page review-workspace" aria-label="小区数据管理">
    <header className="review-heading"><h2>住宅名单与数据采集</h2>
      <CollectionTasksButton jobs={summary?.pipeline ? Object.fromEntries(Object.entries(jobs).filter(([id]) => id !== 'use')) : jobs} errors={jobErrors} onOpen={() => setTasksOpen(true)} /></header>
    {summary?.active === false && <p role="alert" className="directory-warning">新版名单流程尚未启用。需先备份线上数据并核对迁移预演；旧小区和历史数据不会自动删除或重置。</p>}
    <CollectionControls active={!!summary?.active} pipeline={summary?.pipeline} jobs={jobs} errors={jobErrors} busy={busy} action={(...args) => void action(...args)} open={tasksOpen} onOpenChange={setTasksOpen} />
    <CatalogTabs summary={summary} mode={mode} onChange={changeMode} />
    {mode !== 'rental' && <div className="directory-toolbar"><input aria-label="搜索小区名称" placeholder="搜索小区名称、地址" value={q} onChange={e => { setQ(e.target.value); setPage(1); setLoading(true); }} />
      {mode !== 'auctions' && <select aria-label="目录区域" value={district} onChange={e => { setDistrict(e.target.value); setPage(1); setLoading(true); }}><option value="滨江">滨江区</option><option value="萧山">萧山接壤目录</option><option value="">全部区域</option></select>}
      <CatalogClassificationFilter mode={mode} value={mode === 'admitted' ? marketFilter : propertyFilter} propertyTypes={propertyTypes}
        onChange={value => { if (mode === 'admitted') setMarketFilter(value); else setPropertyFilter(value); setPage(1); setLoading(true); }} />
      {(mode === 'admitted' || mode === 'pending') && <select aria-label="高德定位状态" value={positionFilter} onChange={e => { setPositionFilter(e.target.value); setPage(1); setLoading(true); }}><option value="">全部定位状态</option>{Object.entries(positionBucketLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}
      {mode !== 'auctions' && <select aria-label="住宅用途核对状态" value={useFilter} onChange={e => { setUseFilter(e.target.value); setPage(1); setLoading(true); }}><option value="">全部用途核对状态</option>{Object.entries(useReviewFilterLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}
      {mode === 'admitted' && <><select aria-label="法拍数据筛选" value={auctionFilter} onChange={e => { setAuctionFilter(e.target.value); setPage(1); setLoading(true); }}>
        <option value="">全部法拍覆盖</option><option value="has">有法拍记录</option><option value="none">暂无法拍记录</option>
      </select><select aria-label="租金状态筛选" value={rentalFilter} onChange={e => { setRentalFilter(e.target.value); setPage(1); setLoading(true); }}>
        <option value="">全部租金状态</option>{Object.entries(rentalCoverageLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></>}
      {mode === 'auctions' && <label><input type="checkbox" checked={showSkipped} onChange={e => { setShowSkipped(e.target.checked); setPage(1); }} />包含已跳过</label>}
      <button type="button" className="btn btn-secondary directory-refresh" aria-label="刷新名单" title="刷新名单" onClick={() => { setLoading(true); setRevision(v => v + 1); }}>↻</button>
      {mode === 'auctions' && <button className="btn btn-secondary" disabled={busy || !summary?.active} onClick={() => void action('/auctions/associations/sync', 'POST')}>同步历史法拍 / 重试</button>}</div>}
    {error && !detail && !auction && <p role="alert" className="directory-warning">{error}</p>}{notice && <p role="status">{notice}</p>}
    {mode === 'rental' ? (summary?.active ? <RentalAssociationReview onChanged={changed} /> :
      <p role="status" className="directory-muted">名单流程尚未启用，暂无租金待处理清单。</p>) :
    <div className="directory-workspace"><div className="directory-list-panel">
      {loading ? <p role="status">加载名单…</p> : summary?.active && <><p className="directory-muted">当前筛选：{total} 条</p>
        {mode !== 'auctions' ? <CatalogTable items={items} excluded={mode !== 'admitted'} pending={mode === 'pending'} select={row => void select(row)}
          exclude={row => void admissionAction('exclude', row)}
          retry={row => void action(`/directory/workflow/catalog/${encodeURIComponent(row.community_id)}/retry`, 'POST')} busy={busy || !!jobs.amap?.running} position={row => void select(row)} />
          : <div className="directory-table-wrap"><table className="review-table"><thead><tr><th>法拍房产</th><th>地址</th><th>待关联原因</th><th>操作</th></tr></thead><tbody>{auctions.map(r => <tr key={r.id}>
            <td data-label="法拍房产">{r.name}<small>{r.auction_ids?.length || 0} 条轮次{r.skipped ? ' · 已跳过' : ''}</small></td><td data-label="地址">{r.address || '暂无地址'}</td><td data-label="待关联原因">{r.reason}</td>
            <td data-label="操作"><button className="btn btn-secondary" onClick={() => { detailVersion.current += 1; setError(''); setAuction(r); setDetail(null); }}>核对关联</button></td></tr>)}</tbody></table></div>}
        {total === 0 && <p className="directory-empty">没有符合条件的记录。</p>}
        <nav className="directory-actions" aria-label="小区名单分页"><button disabled={page === 1} onClick={() => { setPage(v => v - 1); setLoading(true); }}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(total / 30))} 页</span><button disabled={page * 30 >= total} onClick={() => { setPage(v => v + 1); setLoading(true); }}>下一页</button></nav></>}
    </div>{(detail || auction) && <DirectoryDialog title={detail?.community_name || auction?.name || '查看资料'}
      actions={detail && <button type="button" className="btn btn-secondary" disabled={busy} aria-label="更新资料" title={busy ? '正在更新资料…' : '更新资料：重新拉取透明售房网等来源，并重新判定收录'} onClick={() => void refreshDetail()}>↻</button>}
      footer={detail && (canExclude || resumeAdmission) ? <div className="directory-detail-actions">
        {canExclude && <button className="btn directory-exclude-action" disabled={busy} onClick={() => void admissionAction('exclude')}>确认不收录</button>}
        {resumeAdmission && <button className="btn btn-secondary" disabled={busy} title="恢复后是否收录由透明售房网资料重新判定" onClick={() => void admissionAction('resume')}>恢复自动分类</button>}
      </div> : undefined} onClose={() => { detailVersion.current += 1; setDetail(null); setAuction(null); }}>
      {error && <p role="alert" className="directory-warning">{error}</p>}
      {auction && <AuctionPanel key={`${auction.id}-${auction.revision}`} row={auction} busy={busy} action={(...args) => void action(...args)} />}
      {detail && <><section className="directory-basic-info" aria-label="基本信息">
        <h4>基本信息</h4>
        <dl>
          <div className="directory-info-wide"><dt>小区名称</dt><dd>{detail.community_name}</dd></div>
          <div><dt>区域</dt><dd>{detail.district || '待补充'}</dd></div>
          <div><dt>{detail.collection_pipeline_version ? '透明售房网用途' : '用途'}</dt><dd>{detail.property_types?.join(' / ') || detail.effective_property_type || [...new Set(detail.sources?.filter(s => s.source === 'tmsf').map(s => s.property_type).filter(Boolean))].join(' / ') || '用途资料缺失'}</dd></div>
          {detail.collection_pipeline_version && <div><dt>处理状态</dt><dd>{pipelineStageLabel(detail)}</dd></div>}
          <div><dt>新房 / 二手房</dt><dd>{marketLabels[detail.market_state || 'unknown'] || marketLabels.unknown}</dd></div>
          <div className="directory-info-wide"><dt>实际地址</dt><dd>{detail.address || '待补充'}</dd></div>
        </dl>
        {detail.admission_state === 'admitted' && detail.map_status !== 'displayed' && <p className="directory-warning" role="status">地图暂未展示：{mapLabels[detail.map_status || ''] || '待核对'}</p>}
        {detail.exclusion_reason && <p className="directory-warning">{detail.exclusion_reason}</p>}
      </section>
        {(detail.admission_state === 'admitted' || (detail.collection_pipeline_version && !detail.source_record_id)) && detail.position && <PositionPanel key={`${detail.community_id}-${detail.position.revision}`} position={detail.position} busy={busy || !!jobs.amap?.running} address={detail.geographic_address} communityName={detail.community_name} confirm={body => void positionAction(body)} onQuery={detail.collection_pipeline_version ? () => void queryDetailPosition() : undefined} />}
        {detail.use_review && <UseReviewPanel review={detail.use_review} pipeline={!!detail.collection_pipeline_version} busy={busy || !!jobs.use?.running}
          revision={detail.admission?.revision} open={useConfirmOpen} canConfirm={detail.admission_state !== 'admitted'}
          onToggle={setUseConfirmOpen} onRecheck={() => void reviewAction('recheck')}
          onConfirm={body => void reviewAction('confirm', body)} />}
        <CatalogAuctionRecords coverage={detail.coverage} records={detail.auction_records} />
        <CatalogRentalDetails value={detail.coverage?.rental} />
        <section className="directory-source-section" aria-label="来源资料">
          <div className="directory-source-section-heading"><h4>来源资料</h4></div>
          {notice && <p role="status" className="directory-muted">{notice}</p>}
          {detail.sources?.length ? detail.sources.map(s => <DirectorySourceCard key={s.id} item={s} compact>
            {s.source === 'laipai' && s.status === 'matched' && <button className="btn btn-secondary" disabled={busy} title="解除后这条法拍记录回到待关联列表，可重新核对" onClick={() => void unlinkAuctionSource(s.id)}>解除法拍关联</button>}
          </DirectorySourceCard>) : <p className="directory-muted">暂无来源资料。</p>}
        </section>
      </>}
    </DirectoryDialog>}</div>}
  </section>;
}
