'use client';

import { useEffect, useRef, useState } from 'react';
import { Community, Source, DirectorySourceCard, marketLabels, mapLabels, safeDirectoryLink } from './DirectoryCards';
import PositionPanel, { Position, PositionBadge, positionLabels, positionQueryLabel } from './PositionPanel';
import UseReviewPanel, { UseReview, UseReviewBadge, formatUseReviewMessage } from './UseReviewPanel';
import RentalAssociationReview from '../rental/RentalAssociationReview';
import DirectoryDialog from './DirectoryDialog';
import MergeDialog from './MergeDialog';
import CatalogFilters, { CatalogFilterValues, catalogFilterParams, catalogFiltersForMode, emptyCatalogFilters } from './CatalogFilters';
import { rentalRefreshDiagnostics } from '../../lib/rental-dashboard';
import type { RentalRequestDiagnostics } from '../../lib/rental-types';
import { AuctionCoverage, RentalCoverage, CatalogAuctionRecords, CatalogRentalDetails, type CatalogCoverage, type CatalogAuctionRecord } from './CatalogCoverage';

export type CatalogRow = Community & { property_types?: string[]; position?: Position; use_review?: UseReview;
  merged_to?: string | null;
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
    ['excluded', '不收录', summary?.pipeline ? Math.max(0, summary.excluded - (summary.pending || 0)) : summary?.excluded]];
  return <div className="review-tabs directory-review-states" role="group" aria-label="收录审核状态">{tabs.map(([key, label, count]) =>
    <button key={key} aria-pressed={mode === key} onClick={() => onChange(String(key))}>{count == null ? label : `${label}（${count}）`}</button>)}</div>;
}

export function ManagementTabs({ mode, onChange }: { mode: string; onChange: (mode: string) => void }) {
  const maintenance = mode === 'rental' || mode === 'auctions';
  return <div className="review-tabs" role="group" aria-label="管理工作区">
    <button aria-pressed={!maintenance} onClick={() => { if (maintenance) onChange('admitted'); }}>收录审核</button>
    <button aria-pressed={maintenance} onClick={() => { if (!maintenance) onChange('rental'); }}>小区数据维护</button>
  </div>;
}
type Page<T> = { items: T[]; total: number; page: number; property_types?: string[] };
type Job = RentalRequestDiagnostics & { running: boolean; phase: string; finished_at?: string; started_at?: string; processed?: number; total?: number;
  matched?: number; new?: number; existing?: number; updated?: number; skipped?: number; review?: number; not_found?: number;
  failed?: number; incomplete?: number; conflict?: number; uncertain?: number; requests?: number; skipped_by_state?: Record<string, number>; error?: string;
  retryable?: number; unqueried?: number; mode?: 'all' | 'refresh_all' | 'unqueried' | 'retry_failed' | 'full' | 'incremental';
  incremental_count?: number; current_community_id?: string; current_community_name?: string; current_step?: string;
  diagnostics?: { requests?: number; cache_hits?: number; wait_seconds?: number; http_seconds?: number; elapsed_seconds?: number; early_stop?: boolean };
  resolutions?: Record<string, number>; evidence_issues?: { name?: string; message: string }[];
  position_followup?: { state: string; targets?: number; message?: string };
  stage?: string; association?: { checked?: number; matched?: number; pending?: number; missing?: number; failed?: number; deferred?: number }; errors?: { message: string; name?: string; state?: string; reason?: string }[]; truncated?: { message: string; state?: string; reason?: string }[] };
type IncomingJob = Omit<Job, 'errors'> & { total_communities?: number; processed_communities?: number;
  errors?: Job['errors'] | { items?: { message: string }[]; total?: number } };
export function normalizeCollectionJob(value: IncomingJob | null): Job | null {
  if (!value) return null;
  return { ...value, total: value.total ?? value.total_communities, processed: value.processed ?? value.processed_communities,
    errors: Array.isArray(value.errors) ? value.errors : value.errors?.items || [] };
}
type CollectionTask = { id: string; label: string; short: string; stop: string; path: string; hint: string;
  body?: object; group?: string };
const rentalGroupTitle = '租金流程';
const rentalGroupHint = '先匹配幸福里来源，再更新租金数据；两个动作互斥，不能同时运行。';
const tasks: CollectionTask[] = [
  { id: 'tmsf', label: '住宅名称采集', short: '透明售房网', stop: '停止采集', path: '/directory/collection', hint: '更新全部资料会重新扫描名单、更新用途和挂牌数量；新房采集基本资料后衔接主体匹配，可靠高德主体地址可用于收录。重试失败项仅补采网络获取失败的项目，保留成功项；身份冲突和待地点匹配分开处理。', body: { sources: ['tmsf'] } },
  { id: 'amap', label: '补全高德定位', short: '高德定位', stop: '停止补全定位', path: '/directory/workflow/positions', hint: '仅已收录住宅；批量补待补全和失败项，保留人工结果' },
  { id: 'use', label: '核对住宅用途', short: '用途核对', stop: '停止用途核对', path: '/directory/workflow/use-reviews', hint: '核对用途缺失、其他、冲突、公寓商住等需核实项目及已定位住宅；已有人工决定、明确非住宅和区域异常项不重复查询，发现冲突后由你确认。' },
  { id: 'rentalMatch', label: '匹配租金来源', short: '来源匹配', stop: '停止匹配', path: '/rentals/source-matching', hint: '为缺来源的已收录小区匹配幸福里；有歧义的留待确认，不会采集租金。', group: 'rental' },
  { id: 'rent', label: '更新租金数据', short: '租金更新', stop: '停止更新租金', path: '/rentals/refresh', hint: '仅已收录住宅中已关联幸福里的小区；采集房源并更新租金统计，不会查找或关联来源。', group: 'rental' },
  { id: 'auction', label: '采集法拍', short: '法拍', stop: '停止采集法拍', path: '/auctions/refresh', hint: '采集滨江法拍，匹配住宅，未匹配进入待关联' },
];
type TaskGroup = { id: string; title?: string; hint?: string; tasks: CollectionTask[] };
/** 同一 group 的相邻任务收进同一区块：租金两步（匹配来源 → 更新租金）本是一条流程，不该散在任务列表里。 */
function taskGroups(list: CollectionTask[]): TaskGroup[] {
  return list.reduce<TaskGroup[]>((groups, t) => {
    const last = groups[groups.length - 1];
    if (t.group && last && last.id === t.group) {
      groups[groups.length - 1] = { ...last, tasks: [...last.tasks, t] };
      return groups;
    }
    return [...groups, { id: t.group || t.id, title: t.group ? rentalGroupTitle : undefined,
      hint: t.group ? rentalGroupHint : undefined, tasks: [t] }];
  }, []);
}
const restPhases = ['idle', 'succeeded', 'done'];
const stageLabels: Record<string, string> = { matching: '匹配幸福里来源', checking: '检查租金来源', discovering: '查找租金来源', crawling: '采集租金房源',
  publishing: '发布租金统计', names: '更新小区名录', property_types: '补充用途资料' };
const phases: Record<string, string> = { running: '正在采集', crawling: '正在采集', publishing: '正在发布', checking_sources: '检查来源', idle: '尚未采集',
  succeeded: '采集完成', done: '采集完成', failed: '采集失败', error: '采集失败', partial_failed: '部分完成',
  cancelled: '已取消', interrupted: '服务重启，任务中断', cancelling: '正在取消', cooling_down: '来源冷却中，将自动继续', budget_exhausted: '本轮预算用完，可继续匹配' };

function taskPhase(t: (typeof tasks)[number], job: Job) {
  if (t.id === 'rentalMatch') {
    if (job.phase === 'done') return '匹配完成';
    if (job.phase === 'running') return '正在匹配';
    if (job.phase === 'idle') return '尚未匹配';
    if (job.phase === 'failed') return '匹配失败';
  }
  return phases[job.phase] || job.phase;
}

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
      `补全 ${job.updated || 0} · 待人工确认 ${job.review} · 未找到主体地点 ${job.not_found || 0}${job.failed ? ` · 查询失败 ${job.failed}` : ''}${job.incomplete ? ` · 返回不完整 ${job.incomplete}` : ''}`,
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
  const renderTask = (t: CollectionTask) => {
    const job = jobs[t.id];
    const running = !!job?.running;
    const state = taskStateOf(t, jobs, errors);
    const problem = errors[t.id] || job?.error || '';
    const message = job ? [job.mode === 'retry_failed' && '重试失败项', taskPhase(t, job), taskCounts(t, job)].filter(Boolean).join(' · ') : '';
    const rentalBlocked = (t.id === 'rent' && jobs.rentalMatch?.running) || (t.id === 'rentalMatch' && jobs.rent?.running);
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
        <div className="directory-task-actions"><button className={`btn ${running ? 'btn-secondary' : 'btn-primary'}`} disabled={busy || (!active && !running) || !!rentalBlocked}
          onClick={() => (running ? action(t.path, 'DELETE') : action(t.path, 'POST', t.id === 'amap' ? { mode: 'refresh_all' } : t.id === 'rentalMatch' ? { mode: 'full' } : t.body))}>
          {running ? t.stop : t.id === 'tmsf' ? '更新全部资料' : t.id === 'amap' ? '更新全部' : t.id === 'rentalMatch' ? '全量匹配' : t.id === 'rent' ? t.label : '开始'}</button>
        {t.id === 'rentalMatch' && <button className="btn btn-secondary" data-rental-incremental
          disabled={busy || !active || running || !!rentalBlocked || !job?.incremental_count}
          onClick={() => action(t.path, 'POST', { mode: 'incremental' })}>继续匹配（{job?.incremental_count ?? '—'}）</button>}
        {t.id === 'tmsf' && <button className="btn btn-secondary" disabled={busy || !active || running || !job?.retryable}
          onClick={() => action(t.path, 'POST', { ...t.body, mode: 'retry_failed' })}>
          重试失败项（{job?.retryable || 0}）</button>}
        {t.id === 'amap' && <button className="btn btn-secondary" disabled={busy || !active || running}
          onClick={() => action(t.path, 'POST', { mode: 'unqueried' })}>继续匹配</button>}
        {t.id === 'amap' && <button className="btn btn-secondary" disabled={busy || !active || running || !job?.retryable}
          onClick={() => action(t.path, 'POST', { mode: 'retry_failed' })}>
          重试查询失败（{job?.retryable || 0}）</button>}</div>
      </div>
      <p className="directory-task-hint">{t.hint}<span className="directory-task-lastrun">{lastRun}</span></p>
      {t.id === 'rentalMatch' && <p className="directory-task-sub">全量匹配会重新查询所有缺来源小区；继续匹配只查剩余、新增及失败项，跳过已查完的待选择和未找到项。已关联及人工跳过的小区会保留。</p>}
      {t.id === 'rentalMatch' && job?.diagnostics && <p className="directory-task-sub">
        {job.mode === 'full' ? '全量匹配' : '继续匹配'} · 实际请求 {job.diagnostics.requests || 0} · 复用结果 {job.diagnostics.cache_hits || 0}
        {job.current_community_name && ` · 当前：${job.current_community_name}`}
        {job.current_step && ` · ${{ search: '搜索小区', homepage: '核对主页', resolving_entry: '寻找租房入口', listing_owner: '核验房源', listing_owner_from_list: '核验列表' }[job.current_step] || '正在处理'}`}
      </p>}
      {t.id === 'amap' && <p className="directory-task-sub">当前待处理：尚未查询 {job?.unqueried ?? '—'} 条 → 继续匹配 · 查询失败／不完整 {job?.retryable ?? '—'} 条 → 重试查询失败</p>}
      {t.id === 'amap' && <p className="directory-task-sub">更新全部会重新查询符合条件的楼盘，包括已自动匹配、待确认和未找到的项目，保留人工确认结果；继续匹配只处理尚未查询项目；重试查询失败只处理查询失败或结果不完整的项目。每轮有请求上限。</p>}
      {(problem || message) && <p className="directory-task-line" data-state={state}>
        {problem ? <span role="alert">{problem}</span> : <span role="status">{message}</span>}
      </p>}
      {job?.association && <p className="directory-task-sub">已检查 {job.association.checked || 0} · 已关联 {job.association.matched || 0} · 待选择 {job.association.pending || 0} · 未找到 {job.association.missing || 0} · 查询失败 {job.association.failed || 0} · 未查询 {job.association.deferred || 0}</p>}
      {t.id === 'tmsf' && job?.resolutions && <p className="directory-task-sub">当前资料：基本资料齐备 {job.resolutions.ready || 0} · 非住宅 {job.resolutions.non_residential || 0} · 待地点匹配 {job.resolutions.position_pending || 0} · 身份待核对 {job.resolutions.identity_conflict || 0} · 网络可重试 {job.resolutions.retryable || 0} · 基本资料待取得 {job.resolutions.facts_pending || 0}</p>}
      {t.id === 'tmsf' && job?.position_followup?.state === 'started' && <p className="directory-task-sub">已自动衔接主体匹配（{job.position_followup.targets || 0} 项），进度见地点匹配任务。</p>}
      {t.id === 'tmsf' && job?.position_followup?.state === 'pending' && <p className="directory-task-sub">主体匹配待继续：{job.position_followup.message}</p>}
      {!!job?.evidence_issues?.length && <details className="directory-task-sub"><summary>资料待核对（{job.evidence_issues.length}）</summary>
        {job.evidence_issues.map((item, index) => <p key={index}>{item.name && `${item.name}：`}{item.message}</p>)}</details>}
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
  };
  return <>
    {relevant.length > 0 && <button type="button" className="directory-task-summary"
      data-state={anyFailed ? 'failed' : anyRunning ? 'running' : 'info'}
      aria-haspopup="dialog" onClick={() => onOpenChange(true)}>
      <span className="directory-task-dot" aria-hidden="true" />
      {relevant.map(t => {
        const job = jobs[t.id];
        const problem = errors[t.id] || job?.error || '';
        const message = job ? [job.mode === 'retry_failed' && '重试失败项', taskPhase(t, job), taskCounts(t, job)].filter(Boolean).join(' · ') : '';
        return <span key={t.id}><strong>{t.short}</strong> {problem || message}</span>;
      })}
      <span className="directory-task-more">详情</span>
    </button>}
    {open && <DirectoryDialog title="采集任务" onClose={() => onOpenChange(false)}>
      {!active && <p className="directory-warning">名单流程尚未启用，采集暂不可用。</p>}
      {taskGroups(availableTasks).map(group => group.title
        ? <section key={group.id} className="directory-task-group" aria-label={group.title}>
          <div className="directory-task-group-head"><strong>{group.title}</strong><span>{group.hint}</span></div>
          {group.tasks.map(renderTask)}
        </section>
        : renderTask(group.tasks[0]))}
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

export function pipelineStageLabel(row: Pick<CatalogRow, 'workflow_state' | 'qualification' | 'position'>): string {
  if (row.workflow_state === 'pending' && row.qualification === 'type_uncertain' && row.position && !row.position.selected) {
    if (row.position.query_history) return '待重查地点';
    return row.position.state === 'not_found' ? '未找到主体地点' : row.position.state === 'error' ? '待重查地点'
      : row.position.state === 'review' ? '待确认地点' : '待匹配地点';
  }
  if (row.workflow_state === 'admitted') return '已收录';
  if (row.workflow_state === 'excluded') return '明确不收录';
  return ({ position_pending: '待匹配地点', position_review: '待确认地点', position_type_missing: '待补主体类型',
    use_conflict: '待确认用途', use_uncertain: '待确认用途', type_uncertain: '待确认用途',
    type_missing: '待补用途资料', type_conflict: '待核实用途', region_conflict: '待核实区域' } as Record<string, string>)[row.qualification] || '待补资料';
}

export function catalogCanExclude(row?: Pick<CatalogRow, 'admission_state' | 'workflow_state' | 'qualification' | 'source_record_id' | 'admission'> | null): boolean {
  return !!row && !row.source_record_id && !!row.admission?.revision && row.qualification !== 'manual_exclusion';
}

export function catalogCanConfirmUse(row?: CatalogRow | null): boolean {
  return !!row && !row.source_record_id && !row.deleted && !row.merged_to && !!row.admission?.revision
    && !row.admission.auto_review_locked && row.qualification !== 'manual_exclusion'
    && (row.admission_state !== 'admitted' || !!row.use_review?.re_review);
}

export function CatalogUseReviewSection({ row, busy, open, onToggle, onRecheck, onConfirm }: {
  row: CatalogRow; busy: boolean; open: boolean; onToggle: (open: boolean) => void;
  onRecheck: () => void; onConfirm: (body: object) => void;
}) {
  if (!row.use_review && !catalogCanConfirmUse(row)) return null;
  return <div id={`catalog-use-review-${row.community_id}`}>
    <UseReviewPanel review={row.use_review} pipeline={!!row.collection_pipeline_version}
      missingSubjectType={row.qualification === 'position_type_missing'} busy={busy}
      revision={row.admission?.revision} open={open} canConfirm={catalogCanConfirmUse(row)}
      onToggle={onToggle} onRecheck={onRecheck} onConfirm={onConfirm} />
  </div>;
}

/** 待处理行按操作三桶分类，分支顺序与 pipelineStageLabel 一致，也与后端 operation 筛选对齐：所见即所筛。 */
export function pendingOperationBucket(row: Pick<CatalogRow, 'qualification' | 'position'>): 'position' | 'use' | 'facts' {
  if (row.qualification === 'type_uncertain' && row.position && !row.position.selected) return 'position';
  if (['position_pending', 'position_review', 'position_type_missing'].includes(row.qualification)) return 'position';
  if (['use_conflict', 'use_uncertain', 'type_uncertain'].includes(row.qualification)) return 'use';
  return 'facts';
}

function CatalogAmapType({ position }: { position?: Position }) {
  const selected = position?.selected;
  const candidates = position?.candidates || [];
  const references = position?.reference_candidates || [];
  const types = (points: typeof candidates) => Array.from(new Set(points.map(p => p.poi_type || p.poi_typecode || '类型缺失'))).join(' / ');
  if (selected) return <span>{selected.poi_type || selected.poi_typecode || '类型缺失'}</span>;
  if (candidates.length) return <span className="directory-muted">候选主体 · 待确认</span>;
  if (references.length) return <div>{types(references)}<small className="directory-muted">相关地点 · 仅供参考</small></div>;
  return <span className="directory-muted">{positionQueryLabel(position)}</span>;
}

function addressSourceLabel(c: Community): string {
  const origin = c.address_evidence?.origin;
  return origin === 'amap_subject' ? '高德主体地址' : origin === 'manual' ? '历史确认地址' : origin ? '透明售房网地址' : '';
}

export function CatalogTable({ items, excluded, pending = false, select, busy, position, exclude, selected, onToggle }: { items: CatalogRow[]; excluded: boolean; pending?: boolean;
  select: (row: CatalogRow) => void; busy: boolean; position?: (row: CatalogRow) => void; exclude?: (row: CatalogRow) => void;
  selected?: string[]; onToggle?: (id: string) => void; }) {
  const selectable = !excluded && !!onToggle;
  return <div className="directory-table-wrap"><table className={`review-table catalog-table ${excluded ? 'catalog-excluded' : 'catalog-admitted'}${pending ? ' catalog-pending' : ''}${selectable ? ' catalog-selectable' : ''}`}><thead><tr>
    {selectable && <th>选择</th>}<th>{excluded ? '小区名称' : '小区 / 地址'}</th>{excluded && <th>区域 / 实际地址</th>}<th>{excluded ? '房屋用途' : '新房 / 二手房'}</th>
    <th>高德类型</th>{excluded && <th>{pending ? '待处理操作' : '住宅用途核对'}</th>}<th>{excluded ? pending ? '待处理原因 / 资料状态' : '不收录原因 / 资料状态' : '高德定位'}</th>{!excluded && <><th>法拍</th><th>租金</th></>}{pending && <th>收录决定</th>}<th>操作</th>
  </tr></thead><tbody>{items.map(c => <tr key={c.community_id}>
    {selectable && <td data-label="选择"><input type="checkbox" aria-label={`选择${c.community_name}参与合并`} checked={!!selected?.includes(c.community_id)} onChange={() => onToggle?.(c.community_id)} /></td>}
    <td data-label={excluded ? '小区名称' : '小区 / 地址'}><strong className="catalog-text" title={c.community_name}>{c.community_name}</strong>{!!c.aliases?.length && <small className="catalog-text" title={c.aliases.join(' / ')}>{c.aliases.join(' / ')}</small>}
      {!excluded && <><small className="catalog-text directory-muted" title={c.address || '地址待主体匹配'}>{c.district || '区域待补'} · {c.address || '地址待主体匹配'}</small><small className="directory-muted">{addressSourceLabel(c)}</small></>}</td>
    {excluded && <td data-label="区域 / 实际地址">{c.district || '区域待补'}<small className="catalog-text" title={c.address || '地址待主体匹配'}>{c.address || '地址待主体匹配'}</small><small className="directory-muted">{addressSourceLabel(c)}</small></td>}
    <td data-label={excluded ? '房屋用途' : '新房 / 二手房'}>{excluded
      ? c.property_types?.join(' / ') || c.effective_property_type || [...new Set(c.sources?.filter(s => s.source === 'tmsf').map(s => s.property_type).filter(Boolean))].join(' / ') || '用途资料缺失'
      : marketLabels[c.market_state || 'unknown'] || marketLabels.unknown}</td>
    <td data-label="高德类型"><CatalogAmapType position={c.position} /></td>
    {excluded && <td data-label={pending ? '待处理操作' : '住宅用途核对'}><div className="catalog-inline">
      {pending && <span className={`directory-badge directory-op-${pendingOperationBucket(c)}`}>{pipelineStageLabel(c)}</span>}
      {!pending && <UseReviewBadge review={c.use_review} compact />}
      {!pending && c.collection_pipeline_version && <small className="catalog-text">{pipelineStageLabel(c)}</small>}
      {!pending && c.use_review?.auto_skip_reason && <small className="catalog-text directory-muted">{c.use_review.auto_skip_reason}</small>}
      {!pending && c.use_review?.re_review && <small className="catalog-text directory-muted">有新证据待复审</small>}</div></td>}
    {excluded && <td data-label={pending ? '待处理原因 / 资料状态' : '不收录原因 / 资料状态'}>{c.exclusion_reason}<small>{c.facts_state === 'incomplete' ? '资料待补，可重新获取' : pending ? '待核对' : '条件不符'}</small></td>}
    {!excluded && <td data-label="高德定位"><div className="catalog-inline"><PositionBadge position={c.position} compact />{c.position?.state === 'review' && <button className="btn btn-secondary" disabled={busy} onClick={() => (position || select)(c)}>确认位置</button>}</div></td>}
    {!excluded && <><td data-label="法拍"><AuctionCoverage value={c.coverage?.auction} onView={() => select(c)} /></td>
      <td data-label="租金"><RentalCoverage value={c.coverage?.rental} /></td></>}
    {pending && <td data-label="收录决定">{catalogCanExclude(c) && exclude ? <button className="btn directory-exclude-action" disabled={busy} onClick={() => exclude(c)}>确认不收录</button> : <span className="directory-muted">需先补齐身份</span>}</td>}
    <td data-label="操作"><div className="catalog-inline catalog-row-actions"><button className="btn btn-secondary" onClick={() => select(c)}>查看资料</button></div></td>
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

export default function DirectoryFlowWorkspace({ onChanged, initialSource = '', focusPosition = null }: { onChanged: () => void; initialSource?: string; focusPosition?: { communityId: string; key: number } | null }) {
  const [mode, setMode] = useState(initialSource === 'laipai' ? 'auctions' : 'admitted');
  const [filters, setFilters] = useState<CatalogFilterValues>(() => ({ ...emptyCatalogFilters(), district: '滨江' }));
  const [page, setPage] = useState(1);
  const [useConfirmOpen, setUseConfirmOpen] = useState(false);
  const [propertyTypes, setPropertyTypes] = useState<string[]>([]);
  const [showSkipped, setShowSkipped] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null); const [items, setItems] = useState<CatalogRow[]>([]);
  const [auctions, setAuctions] = useState<Auction[]>([]); const [total, setTotal] = useState(0);
  const [jobs, setJobs] = useState<Record<string, Job | null>>({}); const [jobErrors, setJobErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const [mergeOpen, setMergeOpen] = useState(false); const [mergeRows, setMergeRows] = useState<CatalogRow[]>([]);
  const [detail, setDetail] = useState<CatalogRow | null>(null); const [auction, setAuction] = useState<Auction | null>(null);
  const detailVersion = useRef(0);
  const finishes = useRef<Record<string, string>>({});
  const optimistic = useRef<string | null>(null);
  const changed = () => { detailVersion.current += 1; setRevision(v => v + 1); setDetail(null); setAuction(null); onChanged(); };
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const counts = await workflowRequest<Summary>(`/directory/workflow/summary?${new URLSearchParams({ q: filters.q, district: filters.district })}`, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setSummary(counts);
        if (!counts.active) { setLoading(false); return; }
        if (mode === 'rental') { setLoading(false); return; }
        const path = mode === 'auctions' ? `/directory/workflow/auctions?${new URLSearchParams({ q: filters.q, page: String(page), include_skipped: String(showSkipped) })}`
          : `/directory/workflow/catalog?${new URLSearchParams({ ...catalogScope(mode, counts.pipeline), page: String(page), ...catalogFilterParams(mode, filters) })}`;
        const packet = await workflowRequest<Page<CatalogRow> | Page<Auction>>(path, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (page > 1 && (page - 1) * 30 >= packet.total) { setPage(Math.max(1, Math.ceil(packet.total / 30))); return; }
        if (mode === 'auctions') setAuctions((packet as Page<Auction>).items); else setItems((packet as Page<CatalogRow>).items);
        if (mode === 'excluded' || mode === 'pending') setPropertyTypes(packet.property_types || []);
        setTotal(packet.total); setError(''); setLoading(false);
      } catch (e) { if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : '名单加载失败'); setLoading(false); } }
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [mode, filters, page, showSkipped, revision]);
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
  function changeMode(value: string) { setMode(value); setPage(1); setFilters(current => catalogFiltersForMode(current)); setLoading(true); setDetail(null); setAuction(null); detailVersion.current += 1; setSelection([]); setMergeOpen(false); }
  async function select(row: CatalogRow) {
    const version = ++detailVersion.current;
    setError(''); setNotice(''); setDetail(row); setAuction(null);
    setUseConfirmOpen(catalogCanConfirmUse(row) && ['position_type_missing', 'use_conflict', 'use_uncertain'].includes(row.qualification));
    try {
      const path = `/directory/workflow/catalog/${encodeURIComponent(row.community_id)}`;
      const value = await workflowRequest<CatalogRow>(path);
      if (value.admission_state === 'admitted' || (value.collection_pipeline_version && !value.source_record_id)) value.position = await workflowRequest<Position>(path + '/position');
      if (detailVersion.current === version) setDetail(value);
    }
    catch (e) { if (detailVersion.current === version) setError(e instanceof Error ? e.message : '详情加载失败'); }
  }
  // 地图侧"去核对定位"跳转: 按小区直接打开资料弹框(定位面板在弹框内), 不必在分页列表里找
  useEffect(() => {
    if (!focusPosition) return;
    const cid = focusPosition.communityId;
    let cancelled = false;
    (async () => {
      try {
        const row = await workflowRequest<CatalogRow>(`/directory/workflow/catalog/${encodeURIComponent(cid)}`);
        if (cancelled) return;
        setMode('admitted');
        await select(row);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '定位资料加载失败');
      }
    })();
    return () => { cancelled = true; };
  }, [focusPosition]);

  async function positionAction(body: object) {    if (!detail) return;
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
  const maintenance = mode === 'rental' || mode === 'auctions';
  const selectedRows = mode === 'admitted' ? items.filter(c => selection.includes(c.community_id)) : [];
  return <section className="directory-page review-workspace" aria-label="小区数据管理">
    <header className="review-heading"><h2>住宅名单与数据采集</h2>
      <CollectionTasksButton jobs={summary?.pipeline ? Object.fromEntries(Object.entries(jobs).filter(([id]) => id !== 'use')) : jobs} errors={jobErrors} onOpen={() => setTasksOpen(true)} /></header>
    {summary?.active === false && <p role="alert" className="directory-warning">新版名单流程尚未启用。需先备份线上数据并核对迁移预演；旧小区和历史数据不会自动删除或重置。</p>}
    <CollectionControls active={!!summary?.active} pipeline={summary?.pipeline} jobs={jobs} errors={jobErrors} busy={busy} action={(...args) => void action(...args)} open={tasksOpen} onOpenChange={setTasksOpen} />
    <ManagementTabs mode={mode} onChange={changeMode} />
    {maintenance ? <div className="directory-actions directory-maintenance-filter">
      <label>维护事项<select value={mode} onChange={e => changeMode(e.target.value)}>
        <option value="rental">租金来源</option>
        <option value="auctions">法拍待关联{summary ? `（${summary.auction_pending}）` : ''}</option>
      </select></label>
    </div> : <CatalogTabs summary={summary} mode={mode} onChange={changeMode} />}
    {mode !== 'rental' && <CatalogFilters mode={mode} values={filters} propertyTypes={propertyTypes} total={total} loading={loading}
      onChange={(key, value) => { setFilters(current => ({ ...current, [key]: value })); setPage(1); setLoading(true); setSelection([]); }}
      onRemove={key => { setFilters(current => ({ ...current, [key]: '' })); setPage(1); setLoading(true); setSelection([]); }}
      onClear={() => { setFilters(emptyCatalogFilters()); setPage(1); setLoading(true); setSelection([]); }}
      onRefresh={() => { setLoading(true); setRevision(v => v + 1); }}
      extra={<>
        {mode === 'auctions' && <label><input type="checkbox" checked={showSkipped} onChange={e => { setShowSkipped(e.target.checked); setPage(1); }} />包含已跳过</label>}
        {mode === 'auctions' && <button className="btn btn-secondary" disabled={busy || !summary?.active} onClick={() => void action('/auctions/associations/sync', 'POST')}>同步历史法拍 / 重试</button>}
      </>} />}
    {error && !detail && !auction && <p role="alert" className="directory-warning">{error}</p>}{notice && <p role="status">{notice}</p>}
    {mode === 'rental' ? (summary?.active ? <RentalAssociationReview onChanged={changed} /> :
      <p role="status" className="directory-muted">名单流程尚未启用，暂无租金待处理清单。</p>) :
    <div className="directory-workspace"><div className="directory-list-panel">
      {loading ? <p role="status">加载名单…</p> : summary?.active && <>
        {mode === 'admitted' && selectedRows.length >= 2 && <div className="directory-actions directory-batch">
          <span className="directory-muted">已选 {selectedRows.length} 条</span>
          <button className="btn btn-primary" onClick={() => { setMergeRows(selectedRows); setMergeOpen(true); }}>合并所选（{selectedRows.length}）</button>
          <button className="btn btn-secondary" onClick={() => setSelection([])}>取消选择</button>
        </div>}
        {mode !== 'auctions' ? <CatalogTable items={items} excluded={mode !== 'admitted'} pending={mode === 'pending'} select={row => void select(row)}
          exclude={row => void admissionAction('exclude', row)}
          busy={busy || !!jobs.amap?.running} position={row => void select(row)}
          selected={mode === 'admitted' ? selection : undefined}
          onToggle={mode === 'admitted' ? (id => setSelection(v => v.includes(id) ? v.filter(k => k !== id) : [...v, id])) : undefined} />
          : <div className="directory-table-wrap"><table className="review-table"><thead><tr><th>法拍房产</th><th>地址</th><th>待关联原因</th><th>操作</th></tr></thead><tbody>{auctions.map(r => <tr key={r.id}>
            <td data-label="法拍房产">{r.name}<small>{r.auction_ids?.length || 0} 条轮次{r.skipped ? ' · 已跳过' : ''}</small></td><td data-label="地址">{r.address || '暂无地址'}</td><td data-label="待关联原因">{r.reason}</td>
            <td data-label="操作"><button className="btn btn-secondary" onClick={() => { detailVersion.current += 1; setError(''); setAuction(r); setDetail(null); }}>核对关联</button></td></tr>)}</tbody></table></div>}
        {total === 0 && <p className="directory-empty">没有符合条件的记录。</p>}
        <nav className="directory-actions" aria-label="小区名单分页"><button disabled={page === 1} onClick={() => { setPage(v => v - 1); setLoading(true); setSelection([]); }}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(total / 30))} 页</span><button disabled={page * 30 >= total} onClick={() => { setPage(v => v + 1); setLoading(true); setSelection([]); }}>下一页</button></nav></>}
    </div>{(detail || auction) && <DirectoryDialog title={detail?.community_name || auction?.name || '查看资料'}
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
          <div className="directory-info-wide"><dt>收录地址</dt><dd>{detail.address || '地址待主体匹配'}{addressSourceLabel(detail) && <small className="directory-muted"> · {addressSourceLabel(detail)}</small>}</dd></div>
        </dl>
        {detail.admission_state === 'admitted' && detail.map_status !== 'displayed' && <p className="directory-warning" role="status">地图暂未展示：{mapLabels[detail.map_status || ''] || '待核对'}</p>}
        {detail.exclusion_reason && <p className="directory-warning">{detail.exclusion_reason}</p>}
        {detail.qualification === 'position_type_missing' && catalogCanConfirmUse(detail) && <div className="directory-actions">
          <button className="btn btn-secondary" disabled={busy || !!jobs.use?.running} onClick={() => {
            setUseConfirmOpen(true);
            document.getElementById(`catalog-use-review-${detail.community_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }}>确认住宅用途</button>
        </div>}
      </section>
        {(detail.admission_state === 'admitted' || (detail.collection_pipeline_version && !detail.source_record_id)) && detail.position && <PositionPanel key={`${detail.community_id}-${detail.position.revision}`} position={detail.position} busy={busy || !!jobs.amap?.running} address={detail.geographic_address} communityName={detail.community_name} confirm={body => void positionAction(body)} onQuery={detail.collection_pipeline_version ? () => void queryDetailPosition() : undefined} />}
        <CatalogUseReviewSection key={detail.community_id} row={detail} busy={busy || !!jobs.use?.running} open={useConfirmOpen}
          onToggle={setUseConfirmOpen} onRecheck={() => void reviewAction('recheck')}
          onConfirm={body => void reviewAction('confirm', body)} />
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
    {mergeOpen && <MergeDialog rows={mergeRows} onClose={() => setMergeOpen(false)} onMerged={() => { setSelection([]); changed(); }} />}
  </section>;
}
