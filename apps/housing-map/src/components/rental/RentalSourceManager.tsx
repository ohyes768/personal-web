'use client';

import { useEffect, useRef, useState } from 'react';
import { rentalDataChanged, safeSourceLink, sourcePath, sourceRequest, type RentalSource, type SourceDetail } from '../../lib/rental-sources';

export function SourceCandidate({ candidate, busy, onConfirm, onReject }: {
  candidate: RentalSource; busy: boolean; onConfirm: () => void; onReject: () => void;
}) {
  return <article className="rental-source-candidate">
    <strong>{candidate.source_name}</strong>
    <p>来源地址：{candidate.source_address || '尚不可得，请打开来源核对位置'}</p>
    {candidate.evidence?.map(line => <p className="rental-meta" key={line}>{line}</p>)}
    <div className="rental-source-actions">
      <a href={safeSourceLink(candidate.source_url)} target="_blank" rel="noopener noreferrer">查看房天下来源 ↗</a>
      <button className="btn btn-primary" disabled={busy} onClick={onConfirm}>确认是这个小区</button>
      <button className="btn btn-secondary" disabled={busy} onClick={onReject}>不是这个小区</button>
    </div>
  </article>;
}

export function RentalSourceAssociation({ communityId, onChanged }: { communityId: string; onChanged?: () => void }) {
  const [state, setState] = useState<{ id: string; data?: SourceDetail; error?: string } | null>(null);
  const [keyword, setKeyword] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
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
        setNotice(next.found_count === 0 ? '未找到可确认的候选。可修改关键词，或打开房天下找到小区租房页后粘贴链接。' : '请核对来源名称、位置和分期，再确认关联。');
      } else if (!suffix) {
        setNotice(method === 'DELETE' ? '已解除关联，旧租金不再展示。' : '关联已保存。在“采集任务”里开始“采集租金”即可采集数据。');
        rentalDataChanged();
      }
      onChanged?.();
    } catch (error) {
      if (activeId.current === communityId) setNotice(error instanceof Error ? error.message : '操作失败，请重试');
    } finally { if (activeId.current === communityId) setBusy(false); }
  }
  const searchName = keyword || data?.community?.community_alias || data?.community?.community_name || '';
  return <section className="rental-source-association" aria-label="关联租金来源">
    <h3>租金来源</h3>
    {!current && <p role="status">正在加载来源关联…</p>}
    {current?.error && <p role="alert">{current.error} <button onClick={() => setRetry(v => v + 1)}>重试</button></p>}
    {data && <>
      <p className="rental-meta">地图小区：{data.community?.community_name} · {data.community?.district} {data.community?.subdistrict}</p>
      {data.mapping ? <div className="rental-source-current">
        <strong>已关联：{data.mapping.source_name}</strong>
        <p>{data.mapping.source_address || '地址未记录'} · 确认时间 {data.mapping.verified_at?.slice(0, 10) || '—'}</p>
        <div className="rental-source-actions"><a href={safeSourceLink(data.mapping.source_url)} target="_blank" rel="noopener noreferrer">查看来源 ↗</a>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming('remove')}>解除关联</button></div>
      </div> : <p>尚未关联租金来源。先找到对应小区，确认后在“采集任务”里采集租金。</p>}
      <form onSubmit={e => { e.preventDefault(); void act('POST', '/search', { keyword, source_url: sourceUrl }); }}>
        <label>小区名称或别名<input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder={data.community?.community_alias || data.community?.community_name} maxLength={80} /></label>
        <label>房天下小区租房页链接（可选）<input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} placeholder="https://zu.fang.com/hz/house-xm…/" maxLength={300} /></label>
        <div className="rental-source-actions">
          <button className="btn btn-primary" disabled={busy} type="submit">{busy ? '处理中…' : sourceUrl ? '读取链接候选' : '查找租金来源'}</button>
          <a href="https://zu.fang.com/hz/" target="_blank" rel="noopener noreferrer">打开房天下搜索 ↗</a>
        </div>
        <p className="rental-meta">搜索名称：{searchName}。若自动查找不可用，在房天下搜索后打开小区租房页，复制链接到上方；不需要编辑文件。已排除的候选可再次粘贴链接重新核对。</p>
      </form>
      {data.candidates.map(candidate => <SourceCandidate key={candidate.source_community_id} candidate={candidate} busy={busy}
        onConfirm={() => setConfirming(candidate)} onReject={() => void act('DELETE', `/candidates/${encodeURIComponent(candidate.source_community_id)}`)} />)}
      {confirming && <div className="rental-source-confirm" role="group" aria-label="确认来源变更">
        <p>{confirming === 'remove' ? '解除后，这个小区不会再采集或展示原来源租金。确认解除？' : `请确认“${confirming.source_name}”与地图小区是同一地址、同一分期。${data.mapping ? '确认后将替换现有关联，原租金暂不展示。' : ''}`}</p>
        <button className="btn btn-primary" disabled={busy} onClick={() => void act(confirming === 'remove' ? 'DELETE' : 'PUT', '', confirming === 'remove' ? undefined : { source_community_id: confirming.source_community_id })}>确认{confirming === 'remove' ? '解除' : '关联'}</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming(null)}>返回核对</button>
      </div>}
    </>}
    {notice && <p role="status" className="rental-source-notice">{notice}</p>}
  </section>;
}
