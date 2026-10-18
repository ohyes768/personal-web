'use client';

import { useState } from 'react';

export type AutoReviewEvidence = { source: string; source_id?: string; name?: string; address?: string; property_type?: string; property_type_error?: string };
export type AutoReviewReport = { snapshot_id: string; rule_version: string; executed_at?: string; counts: Record<string, number>;
  items: { candidate_id: string; name: string; action: string; reasons: string[]; evidence: AutoReviewEvidence[]; outcome?: string; error?: string }[] };

export type Source = { id: string; source: string; source_kind: string; source_id: string; name: string;
  address?: string; district?: string; community_id?: string; status: string; method?: string;
  market_state?: string; market_state_url?: string; project_sale_status?: string; market_state_error?: string;
  project_name?: string; project_id?: string; project_property_type?: string; project_property_type_url?: string;
  longitude?: number; latitude?: number; coordinate_error?: string;
  coordinate_evidence?: { source: string; source_id?: string; source_url?: string; captured_at?: string };
  market_state_captured_at?: string;
  evidence?: string[]; source_url?: string; sample_count?: number; candidates?: Community[]; possible_deleted?: string[];
  residential_state?: ResidentialState; property_type?: string; property_type_url?: string;
  poi_type?: string; poi_typecode?: string; residential_hint?: boolean;
  community_name_missing?: boolean; auction_title?: string;
  property_type_captured_at?: string; property_type_error?: string };
export type Community = { community_id: string; community_name: string; aliases?: string[]; district?: string;
  address?: string; deleted?: boolean; sources?: Source[]; eligible?: boolean; evidence?: string[];
  longitude?: number; latitude?: number; has_boundary?: boolean; residential_state?: 'residential' | 'pending' | 'non_residential' | 'deleted' | 'unknown';
  admission?: { state: string; revision: number; decision_kind: string; auto_review_locked: boolean; reason?: string; decided_at?: string;
    rule_version?: string; batch_id?: string; evidence?: AutoReviewEvidence[] };
  market_state?: string; market_state_conflict?: boolean; admission_state?: string; admission_conflict?: boolean; effective_property_type?: string; map_status?: string;
  events?: { seq: number; action: string; created_at: string; payload: { reason?: string } }[] };
export type Report = { running: boolean; phase: string; source?: string; started_at?: string; finished_at?: string; new?: number; existing?: number;
  auto_review?: AutoReviewReport;
  matched?: number; pending?: number; ignored?: number; stage?: string; property_types?: number;
  property_types_failed?: number; property_types_cached?: number; errors?: { source: string; message: string }[];
  truncated?: { source: string; message: string }[] };
export const labels: Record<string, string> = { tmsf: '透明售房网', amap: '高德地图', fang: '房天下', laipai: '来拍 ya' };
export const marketLabels: Record<string, string> = { new_house: '新房项目', second_hand: '二手房', unknown: '新房 / 二手房状态未知' };
export const phaseLabels: Record<string, string> = { running: '正在采集', succeeded: '采集结束', partial_failed: '部分完成',
  failed: '采集失败', cancelled: '已取消', interrupted: '服务重启，采集中断', cancelling: '正在取消' };
const root = '/api/map/directory';
export const admissionLabels: Record<string, string> = { admitted: '已收录住宅', pending: '待审核', excluded: '已排除' };
export const mapLabels: Record<string, string> = { displayed: '地图显示', not_admitted: '尚未收录，不在地图显示',
  missing_coordinates: '缺坐标', check_coordinates: '坐标待核对', outside_scope: '坐标在覆盖范围外',
  check_name: '名称待核对', merged_duplicate: '重复分期已合并显示', inactive: '已删除或合并' };

export function AdmissionControls({ community, busy, onDecision }: { community: Community; busy: boolean;
  onDecision: (action: string, body: object, text: string) => void }) {
  const [reason, setReason] = useState('');
  const [propertyType, setPropertyType] = useState(community.effective_property_type || '住宅');
  if (!community.admission || community.deleted) return null;
  const admission = community.admission;
  const state = community.admission_state || admission.state;
  const decide = (action: string, text: string) => onDecision(action,
    { revision: admission.revision, reason, ...(action === 'admit' ? { property_type: propertyType } : {}) }, text);
  return <section className="directory-linker" aria-label="住宅收录管理">
    <h4>{admissionLabels[state] || '待审核'} · {mapLabels[community.map_status || ''] || '地图状态待确认'}</h4>
    <p className="directory-muted">{admission.decision_kind === 'manual' ? '人工确认' : admission.decision_kind === 'migration' ? '旧资料初始化' : admission.decision_kind === 'automatic' ? '自动收录' : '尚未审核'}
      {admission.reason ? ` · ${admission.reason}` : ''}</p>
    {admission.auto_review_locked && <p className="directory-warning">自动审核已锁定：重新采集和更新资料不会自动收录。</p>}
    {community.admission_conflict && <p className="directory-warning">当前来源用途证据有变化，请核对；人工确认保留。</p>}
    <label>审核原因<input aria-label="审核原因" value={reason} maxLength={300} onChange={e => setReason(e.target.value)} placeholder="排除必填；撤销可填写疑点" /></label>
    {state !== 'excluded' && <label>确认住宅类型<select aria-label="确认住宅类型" value={propertyType} onChange={e => setPropertyType(e.target.value)}>
      {['住宅', '别墅', '排屋'].map(type => <option key={type}>{type}</option>)}</select></label>}
    <div className="directory-actions">
      {state !== 'excluded' && <button className="btn btn-primary" disabled={busy} onClick={() => decide('admit', '确认这是独立住宅小区？确认后解除自动审核锁，坐标有效时在地图显示。')}>确认收录</button>}
      {state === 'admitted' && <button className="btn btn-secondary" disabled={busy} onClick={() => decide('review', '移到待审核？地图停止显示，资料和历史保留，并锁定自动审核。')}>移到待审核</button>}
      {state !== 'excluded' && <button className="btn btn-secondary" disabled={busy || !reason.trim()} onClick={() => decide('exclude', '排除住宅收录？地图停止显示，来源资料及历史保留，可恢复到待审核。')}>排除收录</button>}
      {state === 'excluded' && <button className="btn btn-secondary" disabled={busy} onClick={() => decide('restore-admission', '恢复到待审核？仍保留自动审核锁，不会直接进入地图。')}>恢复到待审核</button>}
      {state === 'pending' && admission.auto_review_locked && <button className="btn btn-secondary" disabled={busy} onClick={() => decide('allow-auto-review', '解除人工审核锁？仍是待审核，之后允许自动审核规则处理。')}>允许重新自动审核</button>}
    </div>
  </section>;
}

export async function request<T>(path: string, method = 'GET', body?: object, signal?: AbortSignal): Promise<T> {
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
export type ResidentialState = 'residential' | 'pending' | 'non_residential' | 'deleted' | 'unknown' | undefined;
export function ResidentialStateBadge({ state }: { state: ResidentialState }) {
  if (state === 'residential') return <span className="directory-badge directory-residential" title="住宅小区">✅ 住宅</span>;
  if (state === 'pending') return <span className="directory-badge directory-pending" title="物业类型待核实">❓ 待核实</span>;
  if (state === 'non_residential') return <span className="directory-badge directory-non-residential" title="非住宅记录">❌ 非住宅</span>;
  if (state === 'deleted') return <span className="directory-muted" title="已删除">—</span>;
  return <span className="directory-muted" title="尚未分类">—</span>;
}
function sourceTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : `${date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}（北京时间）`;
}

export function DirectorySourceCard({ item, children, compact = false }: { item: Source; children?: React.ReactNode; compact?: boolean }) {
  const link = safeDirectoryLink(item.source_url);
  const propertyLink = safeDirectoryLink(item.property_type_url);
  if (compact) {
    const readableLink = item.source === 'tmsf'
      ? propertyLink || safeDirectoryLink(item.project_property_type_url) || safeDirectoryLink(item.market_state_url) || (link && !/\.js(?:[?#]|$)/i.test(new URL(link).pathname) ? link : undefined)
      : link;
    const description = item.source === 'fang' ? '租金来源' : [item.property_type,
      item.market_state && item.market_state !== 'unknown' && marketLabels[item.market_state], item.project_sale_status].filter(Boolean).join(' · ') || '资料待补充';
    return <article className="directory-source-summary">
      <p><span>{labels[item.source] || '历史来源'}</span> · <strong>{item.community_name_missing ? '来源未提供小区名称' : item.name}</strong></p>
      <div className="directory-source-summary-line"><span>{description}</span>{readableLink && <a href={readableLink} target="_blank" rel="noopener noreferrer">查看来源 ↗</a>}</div>
      {item.property_type_error && <p className="directory-warning">{item.property_type_error}；保留上次有效用途证据。</p>}
      {item.market_state_error && <p className="directory-warning">{item.market_state_error}</p>}
      {item.coordinate_error && <p className="directory-warning">{item.coordinate_error}</p>}
      <details><summary>采集详情</summary>
        <p>关联方式：{item.status === 'ignored' ? '已删除' : item.status === 'pending' ? '待关联' : item.method === 'auto' ? '自动关联' : '人工关联'}</p>
        <p>来源 ID：{item.source_id}</p>
        <p>来源地址：{item.address || '尚未取得'}{item.district && ` · ${item.district}`}</p>
        {item.property_type_captured_at && <p>类型采集时间：{sourceTime(item.property_type_captured_at)}</p>}
        {item.market_state_captured_at && <p>项目核验时间：{sourceTime(item.market_state_captured_at)}</p>}
        {item.project_id && <p>新房项目：{item.project_name} · ID {item.project_id}</p>}
        {item.community_name_missing && <p>原始法拍标题：{item.auction_title || item.name}</p>}
        {item.longitude != null && item.latitude != null && <p>来源坐标：{item.longitude}, {item.latitude}</p>}
        {item.coordinate_evidence && <p>位置来源：{item.coordinate_evidence.source} · ID {item.coordinate_evidence.source_id}</p>}
        {item.evidence?.map((e, i) => <p key={i}>{e}</p>)}
      </details>{children}
    </article>;
  }
  return <article className="directory-source-card">
    <div className="directory-source-heading"><span className="directory-badge">{labels[item.source] || '历史来源'}</span>
      <strong>{item.community_name_missing ? '来源未提供小区名称' : item.name}</strong><span className="directory-muted">{item.status === 'ignored' ? '已删除' : item.status === 'pending' ? '待关联' : item.method === 'auto' ? '自动关联' : '人工关联'}</span></div>
    {item.community_name_missing && <p>原始法拍标题：{item.auction_title || item.name}</p>}
    <p className="directory-muted">{item.source_kind} · ID {item.source_id}</p>
    <p>{item.address || '地址尚未取得'} · {item.district || '区域未知'}</p>
    <p>物业类型：{item.property_type || '尚未获取'} · <ResidentialStateBadge state={item.residential_state} /></p>
    {item.property_type_captured_at && <p className="directory-muted">类型采集时间：{item.property_type_captured_at}</p>}
    {item.property_type_error && <p className="directory-warning">{item.property_type_error}；保留上次有效用途证据。</p>}
    <p>{marketLabels[item.market_state || 'unknown'] || marketLabels.unknown}{item.project_sale_status && ` · ${item.project_sale_status}`}</p>
    {item.market_state_captured_at && <p className="directory-muted">项目身份核验时间：{item.market_state_captured_at}</p>}
    {item.project_id && <p className="directory-muted">新房项目：{item.project_name} · ID {item.project_id}</p>}
    {safeDirectoryLink(item.project_property_type_url || item.market_state_url) && <p><a href={item.project_property_type_url || item.market_state_url} target="_blank" rel="noopener noreferrer">查看新房项目证据 ↗</a>{item.project_property_type && ` · ${item.project_property_type}`}</p>}
    {item.market_state_error && <p className="directory-warning">{item.market_state_error}</p>}
    {item.coordinate_error && <p className="directory-warning">{item.coordinate_error}</p>}
    {item.longitude != null && item.latitude != null && <p className="directory-muted">位置：{item.longitude}, {item.latitude}</p>}
    {item.coordinate_evidence && <p className="directory-muted">位置来源：{item.coordinate_evidence.source === 'historical_amap' ? '历史高德地理编码' : '高德地点'} · ID {item.coordinate_evidence.source_id}{safeDirectoryLink(item.coordinate_evidence.source_url) && <> · <a href={item.coordinate_evidence.source_url} target="_blank" rel="noopener noreferrer">查看位置来源 ↗</a></>}</p>}
    {propertyLink && <p><a href={propertyLink} target="_blank" rel="noopener noreferrer">查看物业类型来源 ↗</a></p>}
    {item.source === 'amap' && <p className="directory-evidence">地图分类：{item.poi_type || '暂无分类'}；仅作住宅线索，房屋用途待核实。</p>}
    {item.evidence?.map((e, i) => <p className="directory-evidence" key={i}>{e}</p>)}
    {link && <a href={link} target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a>}
    {children}
  </article>;
}
