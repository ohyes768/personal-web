'use client';

import { useEffect, useRef, useState } from 'react';
import { RENTAL_SOURCE_LABEL, rentalDataChanged, safeSourceLink, sourcePath, sourceRequest, type SourceDetail } from '../../lib/rental-sources';
import { XingfuliProbe } from './XingfuliProbe';

export function RentalSourceAssociation({ communityId, onChanged }: { communityId: string; onChanged?: () => void }) {
  const [state, setState] = useState<{ id: string; data?: SourceDetail; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
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

  async function removeSource() {
    setBusy(true); setNotice('');
    try {
      const next = await sourceRequest<SourceDetail>(sourcePath(communityId), { method: 'DELETE' });
      if (activeId.current !== communityId) return;
      setState({ id: communityId, data: { ...next, community: next.community || data?.community } });
      setRemoving(false);
      setNotice('已解除关联，旧租金不再展示。');
      rentalDataChanged();
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
        <strong>已关联：{data.mapping.source_name} · {RENTAL_SOURCE_LABEL}</strong>
        <p>{data.mapping.source_address || '地址未记录'} · 确认时间 {data.mapping.verified_at?.slice(0, 10) || '—'}</p>
        <div className="rental-source-actions"><a href={safeSourceLink(data.mapping.source_url)} target="_blank" rel="noopener noreferrer">查看来源 ↗</a>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setRemoving(true)}>解除关联</button></div>
      </div> : <p>尚未关联租金来源。先用下方{RENTAL_SOURCE_LABEL}探查，或在“维护采集”中匹配租金来源；关联后再更新租金数据。</p>}
      {removing && <div className="rental-source-confirm" role="group" aria-label="确认来源变更">
        <p>解除后，这个小区不会再采集或展示原来源租金。确认解除？</p>
        <button className="btn btn-primary" disabled={busy} onClick={() => void removeSource()}>确认解除</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => setRemoving(false)}>返回核对</button>
      </div>}
      {!data.mapping && <XingfuliProbe communityId={communityId} onChanged={onChanged} />}
    </>}
    {notice && <p role="status" className="rental-source-notice">{notice}</p>}
  </section>;
}
