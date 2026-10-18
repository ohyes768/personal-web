'use client';

import { useState } from 'react';
import { safeDirectoryLink } from './DirectoryCards';

export type PositionPoint = { source_id?: string; name?: string; address?: string; longitude?: number; latitude?: number;
  source_url?: string; captured_at?: string; geographic_address?: string; name_similarity?: number };
export type Position = { state: string; has_coordinates: boolean; revision?: string; candidates: PositionPoint[];
  selected?: PositionPoint; checked_at?: string; confirmed_at?: string; error?: string };
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

export default function PositionPanel({ position, busy, confirm, address, communityName }: { position: Position; busy: boolean; address?: string; communityName?: string;
  confirm: (body: object) => void }) {
  const [poi, setPoi] = useState('');
  const selected = position.selected;
  const candidate = position.candidates.find(p => p.source_id === poi);
  return <section className="directory-position-panel" aria-label="高德定位详情">
    <div className="directory-position-heading"><h4>高德定位</h4><PositionBadge position={position} compact /></div>
    {selected?.name && selected.name.trim() !== communityName?.trim() && <p>高德名称：{selected.name}</p>}
    {(selected?.address || selected?.geographic_address || address) && <p>高德地址：{selected?.address || selected?.geographic_address || address}</p>}
    {safeDirectoryLink(selected?.source_url) && <p><a href={selected?.source_url} target="_blank" rel="noopener noreferrer">高德查看 ↗</a></p>}
    {!selected && <p className="directory-muted">{position.has_coordinates ? '已有地图坐标' : '暂无地图坐标'}</p>}
    {position.error && <p role="status" className="directory-warning">{position.error}</p>}
    {position.state === 'review' && (position.candidates.length ? <>
      <div className="directory-position-choice">
        <select aria-label="选择高德候选位置" value={poi} disabled={busy || !position.revision} onChange={e => setPoi(e.target.value)}>
          <option value="">请选择候选位置（{position.candidates.length} 个）</option>
          {position.candidates.map((p, i) => <option key={p.source_id || i} value={p.source_id || ''} disabled={!p.source_id || !(p.address || p.geographic_address)}>
            {p.name || '未命名地点'} · {p.address || p.geographic_address || '地址缺失，无法确认'}
          </option>)}
        </select>
        <button className="btn btn-primary" disabled={busy || !position.revision || !candidate || !(candidate.address || candidate.geographic_address)} onClick={() => confirm({ revision: position.revision, poi_id: poi })}>确认位置</button>
      </div>
      {candidate && <p>{candidate.name} · {candidate.address || candidate.geographic_address}
        {safeDirectoryLink(candidate.source_url) && <> · <a href={candidate.source_url} target="_blank" rel="noopener noreferrer">核对高德位置 ↗</a></>}</p>}
      <p className="directory-muted">核对地址与分期后确认，将更新地图位置。</p>
    </> : <p className="directory-muted">暂无可确认的候选位置。</p>)}
  </section>;
}
