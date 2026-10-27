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

export default function PositionPanel({ position, busy, confirm, address, communityName, onQuery }: { position: Position; busy: boolean; address?: string; communityName?: string;
  onQuery?: () => void;
  confirm: (body: object) => void }) {
  const [choice, setChoice] = useState({ poi: '', revision: position.revision, verified: false });
  const poi = choice.revision === position.revision ? choice.poi : '';
  const selected = position.selected;
  const candidate = position.candidates.find(p => p.source_id === poi);
  const needsVerification = !!candidate && !(candidate.address || candidate.geographic_address);
  const verified = choice.revision === position.revision && choice.verified;
  const candidateMapLink = hasPoint(candidate)
    ? `https://uri.amap.com/marker?position=${candidate.longitude},${candidate.latitude}&name=${encodeURIComponent(candidate.name || communityName || '楼盘位置')}&coordinate=gaode&callnative=0`
    : undefined;
  const addr = selected ? selected.address || selected.geographic_address : address;
  const mapLink = safeDirectoryLink(selected?.source_url);
  return <section className="directory-position-panel" aria-label="高德定位详情">
    <div className="directory-position-heading"><h4>高德定位</h4><PositionBadge position={position} compact /></div>
    {selected?.name && selected.name.trim() !== communityName?.trim() && <p>高德名称：{selected.name}</p>}
    {selected && <p>高德主体类型：{selected.poi_type || selected.poi_typecode || '缺少类型，需补充或人工确认用途'}</p>}
    {selected && !addr && position.coordinates_verified && <p className="directory-muted">高德未提供地址，已人工核对地图位置。</p>}
    {!selected && onQuery && <p className="directory-muted">高德主体类型：{position.candidates.length || position.reference_candidates?.length ? '尚未确认，请参考下方地点类型' : '尚未获取高德类型，可点击下方按钮查询'}</p>}
    {position.query_history && <p className="directory-muted">{position.query_history.message}（历史查询记录，不代表已确认主体）</p>}
    {onQuery && <button className="btn btn-secondary" disabled={busy} onClick={onQuery}>匹配楼盘地点与类型</button>}
    {addr ? <p className="directory-source-summary-line"><span>高德地址：{addr}</span>{mapLink && <a href={mapLink} target="_blank" rel="noopener noreferrer">高德查看 ↗</a>}</p>
      : mapLink && <p><a href={mapLink} target="_blank" rel="noopener noreferrer">高德查看 ↗</a></p>}
    {!selected && <p className="directory-muted">{position.has_coordinates ? '已有地图坐标' : '暂无地图坐标'}</p>}
    {position.error && <p role="status" className="directory-warning">{position.error}</p>}
    {!selected && position.candidates.length > 0 && <div className="directory-position-types">
      <p>候选主体类型（确认地点后用于分类）</p>
      {position.candidates.map((p, i) => <p key={p.source_id || i}>{p.name || '未命名地点'} · {p.poi_type || p.poi_typecode || '高德未提供类型'}</p>)}
    </div>}
    {!!position.reference_candidates?.length && <div className="directory-position-types">
      <p>名称相关地点类型（参考）</p>
      {position.reference_candidates.map((p, i) => <p key={p.source_id || i}>{p.name || '未命名地点'} · {p.poi_type || p.poi_typecode || '高德未提供类型'}
        {p.address && <> · {p.address}</>}</p>)}
      <p className="directory-muted">这些地点尚未确认为楼盘主体，类型供人工判断用途参考。</p>
    </div>}
    {position.state === 'review' && (position.candidates.length ? <>
      <div className="directory-position-choice">
        <select aria-label="选择高德候选位置" value={poi} disabled={busy || !position.revision}
          onChange={e => setChoice({ poi: e.target.value, revision: position.revision, verified: false })}>
          <option value="">请选择候选位置（{position.candidates.length} 个）</option>
          {position.candidates.map((p, i) => <option key={p.source_id || i} value={p.source_id || ''} disabled={!p.source_id || !hasPoint(p)}>
            {p.name || '未命名地点'} · {p.address || p.geographic_address || '地址缺失，需核对地图位置'}{p.poi_type ? ` · ${p.poi_type}` : ''}{p.name_matched === false ? '（名称不匹配，请人工核对）' : ''}
          </option>)}
        </select>
        <button className="btn btn-primary" disabled={busy || !position.revision || !candidate || !hasPoint(candidate) || (needsVerification && !verified)}
          onClick={() => confirm({ revision: position.revision, poi_id: poi, ...(needsVerification ? { coordinates_verified: verified } : {}) })}>确认位置</button>
      </div>
      {candidate && <p>{candidate.name}{(candidate.address || candidate.geographic_address) && <> · {candidate.address || candidate.geographic_address}</>}
        {candidate.name_matched === false && <span>（名称不匹配，请人工核对）</span>}
        {candidateMapLink && <> · <a href={candidateMapLink} target="_blank" rel="noopener noreferrer">核对高德位置 ↗</a></>}</p>}
      {needsVerification && candidate && <div>
        <p className="directory-warning">高德未提供地址，请打开地图核对位置与楼盘范围。</p>
        <p>地图坐标（GCJ02）：{candidate.longitude},{candidate.latitude}</p>
        <label><input type="checkbox" checked={verified} disabled={busy || !position.revision || !hasPoint(candidate)}
          onChange={e => setChoice({ poi, revision: position.revision, verified: e.target.checked })} /> 已核对地图位置，确认是该楼盘</label>
      </div>}
      <p className="directory-muted">核对地址与分期后确认，将更新地图位置。</p>
    </> : <p className="directory-muted">区内未找到相关地点，结果可能不完整，待高德数据完善后重新查询。</p>)}
  </section>;
}
