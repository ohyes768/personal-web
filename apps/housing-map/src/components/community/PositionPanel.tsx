'use client';

import { useState } from 'react';
import { safeDirectoryLink } from './DirectoryCards';

export type PositionPoint = { source_id?: string; name?: string; address?: string; longitude?: number; latitude?: number;
  source_url?: string; captured_at?: string; geographic_address?: string; name_similarity?: number };
export type Position = { state: string; has_coordinates: boolean; revision?: string; candidates: PositionPoint[];
  selected?: PositionPoint; checked_at?: string; confirmed_at?: string; error?: string };
export const positionLabels: Record<string, string> = { matched: '已匹配', pending: '待补全', review: '待确认',
  not_found: '未找到', error: '查询失败', manual: '人工已确认' };

export function PositionBadge({ position }: { position?: Position }) {
  return <><span className="directory-badge">{positionLabels[position?.state || 'pending'] || '待补全'}</span>
    <small>{position?.has_coordinates ? '已有地图坐标' : '缺少地图坐标'}</small>
    {position?.state === 'pending' && position.has_coordinates && <small>历史坐标不代表已匹配 POI</small>}</>;
}

export default function PositionPanel({ position, busy, query, confirm }: { position: Position; busy: boolean;
  query: () => void; confirm: (body: object) => void }) {
  const [poi, setPoi] = useState('');
  const [lng, setLng] = useState(''); const [lat, setLat] = useState(''); const [address, setAddress] = useState('');
  const selected = position.selected;
  return <section className="directory-linker" aria-label="高德定位详情">
    <h4>高德定位 · {positionLabels[position.state] || '待补全'}</h4>
    <p className="directory-muted">定位资料用于已收录小区，不作为小区名单来源。历史坐标与高德 POI 匹配分别记录。</p>
    {selected && <article className="directory-source-card"><strong>{selected.name || '已确认位置'}</strong>
      <p>高德地图地址：{selected.address || selected.geographic_address || '暂无'}</p>
      <p>{selected.source_id ? `POI ID：${selected.source_id}` : '人工坐标，无 POI ID'}</p>
      <p>GCJ02：{selected.longitude}, {selected.latitude}</p>
      {selected.captured_at && <p className="directory-muted">POI 资料时间：{selected.captured_at.slice(0, 19).replace('T', ' ')}（UTC）</p>}
      {safeDirectoryLink(selected.source_url) && <a href={selected.source_url} target="_blank" rel="noopener noreferrer">在高德查看 ↗</a>}
    </article>}
    {position.checked_at && <p className="directory-muted">最近查询：{position.checked_at.slice(0, 19).replace('T', ' ')}（UTC）</p>}
    {position.confirmed_at && <p className="directory-muted">人工确认：{position.confirmed_at.slice(0, 19).replace('T', ' ')}（UTC）</p>}
    {position.error && <p role="status" className="directory-warning">{position.error}</p>}
    {position.state === 'manual' ? <p className="directory-muted">人工结果已保护，批量补全不会覆盖。需要改位置时请重新选择候选或填写坐标。</p>
      : <button className="btn btn-secondary" disabled={busy || !position.revision} onClick={query}>{position.state === 'pending' ? '补全高德 POI' : '重新匹配'}</button>}
    {!!position.candidates.length && <fieldset disabled={busy || !position.revision}><legend>核对高德候选</legend>
      {position.candidates.map(p => <label className="directory-source-card" key={p.source_id}>
        <input type="radio" name="position-poi" checked={poi === p.source_id} onChange={() => setPoi(p.source_id || '')} />
        <strong>{p.name}</strong><p>{p.address || '地图地址缺失'}</p><small>{p.longitude}, {p.latitude} · POI {p.source_id}{p.name_similarity != null ? ` · 相似度 ${p.name_similarity.toFixed(2)}` : ''}</small>
        {safeDirectoryLink(p.source_url) && <p><a href={p.source_url} target="_blank" rel="noopener noreferrer">查看候选位置 ↗</a></p>}
      </label>)}
      <p className="directory-muted">确认前请核对地址与分期；确认后以所选地点更新地图位置。</p>
      <button className="btn btn-primary" disabled={!poi} onClick={() => confirm({ revision: position.revision, poi_id: poi })}>确认所选位置</button>
    </fieldset>}
    <details><summary>手动定位</summary><p className="directory-muted">填写核实后的 GCJ02 坐标和地图地址，保存后受人工保护。</p>
      <label>地图地址<input aria-label="手动地图地址" value={address} onChange={e => setAddress(e.target.value)} maxLength={300} /></label>
      <label>经度<input aria-label="手动经度" inputMode="decimal" value={lng} onChange={e => setLng(e.target.value)} /></label>
      <label>纬度<input aria-label="手动纬度" inputMode="decimal" value={lat} onChange={e => setLat(e.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy || !position.revision || !address.trim() || !lng.trim() || !lat.trim() || !Number.isFinite(Number(lng)) || !Number.isFinite(Number(lat))}
        onClick={() => confirm({ revision: position.revision, longitude: Number(lng), latitude: Number(lat), address: address.trim() })}>确认手动位置</button>
    </details>
  </section>;
}
