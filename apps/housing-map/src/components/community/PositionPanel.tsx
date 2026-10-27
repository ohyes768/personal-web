'use client';

import { useState } from 'react';
import { safeDirectoryLink } from './DirectoryCards';

export type PositionPoint = { source_id?: string; name?: string; address?: string; longitude?: number; latitude?: number;
  source_url?: string; captured_at?: string; geographic_address?: string; name_similarity?: number; name_matched?: boolean;
  poi_typecode?: string; poi_type?: string };
export type Position = { state: string; has_coordinates: boolean; revision?: string; candidates: PositionPoint[];
  selected?: PositionPoint; checked_at?: string; confirmed_at?: string; error?: string;
  query_history?: { state: string; checked_at?: string; message: string };
  coordinates_verified?: boolean;
  reference_candidates?: PositionPoint[] };

export function positionQueryLabel(position?: Position): string {
  if (position?.state === 'error') return '查询失败';
  if (position?.state === 'not_found') return '未找到主体地点';
  if (position?.state === 'review') return '待确认地点';
  if (position?.query_history) return position.query_history.message;
  return position?.checked_at ? '未获取类型' : '未查询';
}
export const positionLabels: Record<string, string> = { matched: '已匹配', pending: '待补全', review: '待确认',
  not_found: '未找到', error: '查询失败', manual: '人工已确认' };
export const positionBucketLabels: Record<string, string> = { done: '已定位', review: '待确认', todo: '待处理' };

export function positionBucket(state?: string): 'done' | 'review' | 'todo' {
  return state === 'matched' || state === 'manual' ? 'done' : state === 'review' ? 'review' : 'todo';
}

export function PositionBadge({ position, compact = false }: { position?: Position; compact?: boolean }) {
  const state = position?.state || 'pending';
  const bucket = positionBucket(state);
  if (compact) return <span className={`directory-badge directory-position-${bucket}`}
    title={`${positionLabels[state] || '待补全'} · ${position?.has_coordinates ? '已有地图坐标' : '缺少地图坐标'}${state === 'pending' && position?.has_coordinates ? ' · 历史坐标不代表已匹配 POI' : ''}`}>
    {positionBucketLabels[bucket]}</span>;
  return <><span className={`directory-badge directory-position-${bucket}`}>{positionBucketLabels[bucket]}</span>
    <small>{positionLabels[state] || '待补全'}</small>
    {bucket !== 'done' && <small>{position?.has_coordinates ? '已有地图坐标' : '缺少地图坐标'}</small>}
    {state === 'pending' && position?.has_coordinates && <small>历史坐标不代表已匹配 POI</small>}</>;
}

function hasPoint(point?: PositionPoint): point is PositionPoint & { longitude: number; latitude: number } {
  return typeof point?.longitude === 'number' && Number.isFinite(point.longitude) && Math.abs(point.longitude) <= 180
    && typeof point.latitude === 'number' && Number.isFinite(point.latitude) && Math.abs(point.latitude) <= 90;
}

/** 高德类型是分级串（如“公司企业;公司;公司”）：卡片只显示末级，完整类型放进可展开详情。 */
export function positionLeafType(point?: PositionPoint): string {
  const parts = (point?.poi_type || '').split(';').map(part => part.trim()).filter(Boolean);
  return parts[parts.length - 1] || point?.poi_typecode || '类型缺失';
}

export function positionFullType(point?: PositionPoint): string {
  const raw = (point?.poi_type || '').trim();
  return raw ? (point?.poi_typecode ? `${raw} · ${point.poi_typecode}` : raw) : point?.poi_typecode || '类型缺失';
}

export type PositionStatusTone = 'info' | 'caution' | 'error';

/** 顶部只用一句话说明当前结果；警示与错误分开，不从旧文案反推“缺地址”。 */
export function positionStatusSummary(position: Position, canQuery = false, selectedPoi = ''): { text: string; tone: PositionStatusTone } {
  const candidates = position.candidates || [];
  const references = position.reference_candidates || [];
  if (position.state === 'error') return { text: '高德查询失败，未能取得地点与类型。', tone: 'error' };
  if (position.state === 'not_found') {
    return references.length
      ? { text: '未找到可确认主体，仅有相关地点可供参考。', tone: 'caution' }
      : { text: '未找到匹配的高德主体地点。', tone: 'caution' };
  }
  if (position.state === 'review') {
    // 已选定候选后，说明当前这个候选还差什么，不再停留在“需要选择”。
    const chosen = candidates.find(point => point.source_id === selectedPoi);
    if (chosen) {
      if (!(chosen.address || chosen.geographic_address)) return { text: '已选候选未提供地址，需要先查看地图核对位置。', tone: 'caution' };
      if (chosen.name_matched === false) return { text: '已选候选名称与楼盘不一致，需要人工核对。', tone: 'caution' };
      return { text: `已选候选「${chosen.name || '未命名地点'}」，核对地图后即可确认。`, tone: 'info' };
    }
    if (candidates.length > 1) return { text: `找到 ${candidates.length} 个候选主体，需要你选择其中之一。`, tone: 'caution' };
    if (candidates.length === 1) {
      const only = candidates[0];
      if (!(only.address || only.geographic_address)) return { text: '唯一候选未提供地址，需要先查看地图核对位置。', tone: 'caution' };
      if (only.name_matched === false) return { text: '唯一候选名称与楼盘不一致，需要人工核对。', tone: 'caution' };
      return { text: '找到 1 个候选主体，核对地图后即可确认。', tone: 'info' };
    }
    if (references.length) return { text: '未找到可确认主体，仅有相关地点可供参考。', tone: 'caution' };
    return { text: '未找到候选主体，可稍后重新查询。', tone: 'caution' };
  }
  if (position.state === 'matched') return { text: '已匹配到高德主体地点。', tone: 'info' };
  if (position.state === 'manual') return { text: '已人工确认地图位置。', tone: 'info' };
  if (position.query_history) return { text: position.query_history.message, tone: 'caution' };
  // 未查询与查过但没取到类型是两种状态，保留区分。
  if (position.checked_at) return { text: '已查询过但尚未获取高德类型，可重新查询。', tone: 'caution' };
  return { text: canQuery ? '尚未获取高德类型，可点击下方按钮查询。' : '尚未获取高德类型。', tone: 'info' };
}

export type PositionChoice = { poi: string; revision?: string; verifiedFor?: string };

/**
 * 选择与核对标记都绑定 revision + POI ID：
 * 候选列表或 revision 变化时，选择回到唯一可用候选（多候选则不选），核对标记一律失效。
 */
export function positionChoiceState(candidates: PositionPoint[], choice: PositionChoice, revision?: string) {
  const usable = candidates.filter(point => !!point.source_id && hasPoint(point));
  const auto = candidates.length === 1 && usable.length === 1 ? String(usable[0].source_id) : '';
  const sameRevision = choice.revision === revision;
  const kept = sameRevision && candidates.some(point => point.source_id === choice.poi) ? choice.poi : '';
  const poi = kept || auto;
  const verified = sameRevision && !!poi && choice.verifiedFor === poi;
  return { poi, verified };
}

/** 确认按钮的禁用原因：总是给出具体一句，而不是只把按钮变灰。 */
export function positionConfirmBlocker(input: { busy: boolean; revision?: string; candidates: PositionPoint[]; poi: string; verified: boolean }) {
  if (input.busy) return '正在处理中，请稍候。';
  if (!input.revision) return '缺少定位版本，请重新查询后再确认。';
  const candidate = input.candidates.find(point => point.source_id === input.poi);
  if (!candidate) {
    if (input.candidates.length === 0) return '没有可确认的候选主体。';
    if (input.candidates.length > 1) return '请先选择要确认的候选主体。';
  }
  if (!candidate?.source_id) return '该候选缺少高德 POI 标识，无法确认。';
  if (!hasPoint(candidate)) return '该候选缺少有效坐标，无法确认。';
  if (!(candidate.address || candidate.geographic_address) && !input.verified) return '请先查看地图并勾选已核对位置。';
  return '';
}

/** 确认请求体：沿用 revision + poi_id，只有无地址候选才附带人工核对标记。 */
export function positionConfirmPayload(input: { revision?: string; poi: string; candidate?: PositionPoint; verified: boolean }) {
  const needsVerification = !!input.candidate && !(input.candidate.address || input.candidate.geographic_address);
  return { revision: input.revision, poi_id: input.poi, ...(needsVerification ? { coordinates_verified: input.verified } : {}) };
}

export default function PositionPanel({ position, busy, confirm, address, communityName, onQuery }: { position: Position; busy: boolean; address?: string; communityName?: string;
  onQuery?: () => void;
  confirm: (body: object) => void }) {
  const [choice, setChoice] = useState<PositionChoice>({ poi: '', revision: position.revision });
  const candidates = position.candidates || [];
  const references = position.reference_candidates || [];
  const selected = position.selected;
  const { poi, verified } = positionChoiceState(candidates, choice, position.revision);
  const candidate = candidates.find(point => point.source_id === poi);
  const needsVerification = !!candidate && !(candidate.address || candidate.geographic_address);
  const candidateMapLink = hasPoint(candidate)
    ? `https://uri.amap.com/marker?position=${candidate.longitude},${candidate.latitude}&name=${encodeURIComponent(candidate.name || communityName || '楼盘位置')}&coordinate=gaode&callnative=0`
    : undefined;
  const addr = selected ? selected.address || selected.geographic_address : address;
  const mapLink = safeDirectoryLink(selected?.source_url);
  const status = positionStatusSummary(position, !!onQuery, poi);
  const blocker = positionConfirmBlocker({ busy, revision: position.revision, candidates, poi, verified });
  const pick = (id: string) => setChoice({ poi: id, revision: position.revision });
  return <section className="directory-position-panel" aria-label="高德定位详情">
    <div className="directory-position-heading"><h4>高德定位</h4><PositionBadge position={position} compact /></div>
    <p className={`directory-position-status directory-position-status-${status.tone}`}>{status.text}</p>
    {position.query_history && <p className="directory-muted">{position.query_history.message}（历史查询记录，不代表已确认主体）</p>}
    {onQuery && <button className="btn btn-secondary" disabled={busy} onClick={onQuery}>匹配楼盘地点与类型</button>}
    {selected?.name && selected.name.trim() !== communityName?.trim() && <p>高德名称：{selected.name}</p>}
    {selected && <p>高德主体类型：{selected.poi_type || selected.poi_typecode || '缺少类型，需补充或人工确认用途'}</p>}
    {addr ? <p className="directory-source-summary-line"><span>高德地址：{addr}</span>{mapLink && <a href={mapLink} target="_blank" rel="noopener noreferrer">高德查看 ↗</a>}</p>
      : mapLink && <p><a href={mapLink} target="_blank" rel="noopener noreferrer">高德查看 ↗</a></p>}
    {selected && !addr && position.coordinates_verified && <p className="directory-muted">高德未提供地址，已人工核对地图位置。</p>}
    {!selected && <p className="directory-muted">{position.has_coordinates ? '已有地图坐标' : '暂无地图坐标'}</p>}
    {position.error && <p role="status" className="directory-warning">{position.error}</p>}
    {position.state === 'review' && candidates.length > 0 && <>
      <fieldset className="directory-candidate-list">
        <legend>候选主体（{candidates.length}）</legend>
        {candidates.map((point, index) => <div key={point.source_id || index} className="directory-candidate-card"
          data-selected={point.source_id === poi}>
          <label className="directory-candidate-pick">
            <input type="radio" name="position-candidate" value={point.source_id || ''} checked={!!point.source_id && point.source_id === poi}
              disabled={busy || !point.source_id || !hasPoint(point)} onChange={() => pick(String(point.source_id))} />
            <span className="directory-candidate-name">{point.name || '未命名地点'}</span>
          </label>
          <div className="directory-candidate-lines">
            <span>地址：{point.address || point.geographic_address || '高德未提供地址'}</span>
            <span>类型：{positionLeafType(point)}</span>
            {point.name_matched === false && <span className="directory-caution">名称与楼盘不一致，需人工核对</span>}
          </div>
          <details className="directory-candidate-detail"><summary>完整类型</summary>
            <p>{positionFullType(point)}</p>
          </details>
        </div>)}
      </fieldset>
      {candidate && <div className="directory-position-review">
        <p className="directory-muted">当前核对：{candidate.name || '未命名地点'} · {candidate.address || candidate.geographic_address || '高德未提供地址'}</p>
        {candidateMapLink && <p><a href={candidateMapLink} target="_blank" rel="noopener noreferrer">查看精确坐标 ↗</a></p>}
        <details className="directory-position-coords"><summary>查看坐标</summary>
          <p>地图坐标（GCJ02）：{candidate.longitude},{candidate.latitude}</p>
        </details>
        {needsVerification && <div className="directory-position-verify">
          <p className="directory-caution">高德未提供地址，请先打开地图核对位置与楼盘范围。</p>
          <label><input type="checkbox" checked={verified} disabled={busy || !position.revision || !hasPoint(candidate)}
            onChange={event => setChoice({ poi, revision: position.revision, verifiedFor: event.target.checked ? poi : undefined })} /> 已核对地图位置，确认是该楼盘</label>
        </div>}
      </div>}
      <div className="directory-position-confirm">
        <button className="btn btn-primary" disabled={!!blocker}
          onClick={() => confirm(positionConfirmPayload({ revision: position.revision, poi, candidate, verified }))}>确认此地点</button>
        {blocker && <span className="directory-position-blocker">{blocker}</span>}
      </div>
    </>}
    {position.state === 'review' && candidates.length === 0 && <p className="directory-muted">区内未找到相关地点，结果可能不完整，待高德数据完善后重新查询。</p>}
    {references.length > 0 && <details className="directory-position-references">
      <summary>相关地点，仅供参考（{references.length}）</summary>
      {references.map((point, index) => <p key={point.source_id || index}>
        {point.name || '未命名地点'} · {positionFullType(point)}{point.address && <> · {point.address}</>}
      </p>)}
      <p className="directory-muted">这些地点尚未确认为楼盘主体，不能直接确认位置。</p>
    </details>}
  </section>;
}
