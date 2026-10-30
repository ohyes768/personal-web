'use client';

import { useEffect, useRef, useState } from 'react';
import { rentalDataChanged, safeSourceLink, sourcePath, sourceRequest, type RentalSource, type SourceDetail } from '../../lib/rental-sources';
import { XingfuliProbe } from './XingfuliProbe';

export function SourceCandidate({ candidate, busy, onConfirm, onReject }: {
  candidate: RentalSource; busy: boolean; onConfirm: () => void; onReject: () => void;
}) {
  return <article className="rental-source-candidate">
    <strong>{candidate.source_name}</strong>
    <p>来源地址：{candidate.source_address || '尚不可得，请打开来源核对位置'}</p>
    {candidate.evidence?.map(line => <p className="rental-meta" key={line}>{line}</p>)}
    <div className="rental-source-actions">
      <a href={safeSourceLink(candidate.source_url)} target="_blank" rel="noopener noreferrer">查看{candidate.source === 'xingfuli' ? '幸福里' : '房天下'}来源 ↗</a>
      <button className="btn btn-primary" disabled={busy} onClick={onConfirm}>确认是这个小区</button>
      <button className="btn btn-secondary" disabled={busy} onClick={onReject}>不是这个小区</button>
    </div>
  </article>;
}

export function RentalSourceAssociation({ communityId, onChanged }: { communityId: string; onChanged?: () => void }) {
  const [state, setState] = useState<{ id: string; data?: SourceDetail; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<RentalSource | 'remove' | null>(null);
  const [notice, setNotice] = useState('');
  const [retry, setRetry] = useState(0);
  const activeId = useRef(communityId);
  useEffect(() => { activeId.current = communityId; return () => { activeId.current = ''; }; }, [communityId]);
  useEffect(() => {
    const controller = new AbortController();
    sourceRequest<SourceDetail>(sourcePath(communityId), { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ id: communityId, data }); })
      .catch(error => { if (!controller.signal.aborted) setState({ id: communityId, error: error.message }); });
    return () => controller.abort();
  }, [communityId, retry]);
  const current = state?.id === communityId ? state : null;
  const data = current?.data;

  async function act(method: string, suffix = '', body?: object) {
    setBusy(true); setNotice('');
    try {
      const next = await sourceRequest<SourceDetail>(sourcePath(communityId) + suffix, {
        method, ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
      if (activeId.current !== communityId) return;
      setState({ id: communityId, data: { ...next, community: next.community || data?.community } });
      setConfirming(null);
      if (suffix === '/search') {
        setNotice(next.found_count === 0 ? '未找到可确认的候选。可修改关键词后重试，或用下方“探查幸福里来源”。' : '请核对来源名称、位置和分期，再确认关联。');
      } else if (!suffix) {
        setNotice(method === 'DELETE' ? '已解除关联，旧租金不再展示。' : '关联已保存。在“维护采集”里开始“更新租金数据”即可采集数据。');
        rentalDataChanged();
      }
      onChanged?.();
    } catch (error) {
      if (activeId.current === communityId) setNotice(error instanceof Error ? error.message : '操作失败，请重试');
    } finally { if (activeId.current === communityId) setBusy(false); }
  }
  return <section className="rental-source-association" aria-label="关联租金来源">
    <h3>租金来源</h3>
    {!current && <p role="status">正在加载来源关联…</p>}
    {current?.error && <p role="alert">{current.error} <button onClick={() => setRetry(v => v + 1)}>重试</button></p>}
    {data && <>
      <p className="rental-meta">地图小区：{data.community?.community_name} · {data.community?.district} {data.community?.subdistrict}</p>
      {data.mapping ? <div className="rental-source-current">
        <strong>已关联：{data.mapping.source_name} · {data.mapping.source === 'xingfuli' ? '幸福里' : '房天下'}</strong>
        <p>{data.mapping.source_address || '地址未记录'} · 确认时间 {data.mapping.verified_at?.slice(0, 10) || '—'}</p>
        <div className="rental-source-actions"><a href={safeSourceLink(data.mapping.source_url)} target="_blank" rel="noopener noreferrer">查看来源 ↗</a>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming('remove')}>解除关联</button></div>
      </div> : <p>尚未关联租金来源。先用下方幸福里探查，或在“维护采集”中匹配租金来源；关联后再更新租金数据。</p>}
      {confirming && <div className="rental-source-confirm" role="group" aria-label="确认来源变更">
        <p>{confirming === 'remove' ? '解除后，这个小区不会再采集或展示原来源租金。确认解除？' : `请确认“${confirming.source_name}”与地图小区是同一地址、同一分期。${data.mapping ? '确认后将替换现有关联，原租金暂不展示。' : ''}`}</p>
        <button className="btn btn-primary" disabled={busy} onClick={() => void act(confirming === 'remove' ? 'DELETE' : 'PUT', '', confirming === 'remove' ? undefined : { source_community_id: confirming.source_community_id })}>确认{confirming === 'remove' ? '解除' : '关联'}</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming(null)}>返回核对</button>
      </div>}
      {!data.mapping && <XingfuliProbe communityId={communityId} onChanged={onChanged} />}
    </>}
    {notice && <p role="status" className="rental-source-notice">{notice}</p>}
  </section>;
}
