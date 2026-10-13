'use client';

import { useEffect, useState } from 'react';
import { fetchAuctionData, type AuctionListData } from '../../lib/auction-types';
import { amount, date, riskLabels, SafeLink, statuses } from '../community/CommunityAuctionHistory';
import AuctionPendingAssociations from './AuctionPendingAssociations';

export function AuctionListContent({ data, onView }: { data: AuctionListData; onView: (id: string) => void }) {
  if (!data.available) return <div className="auction-empty">尚未采集法拍数据，可点击顶部「法拍刷新」。</div>;
  return <>
    <div className="auction-list-count"><strong>累计 {data.overall_total} 条拍卖记录</strong><span>当前筛选 {data.total} 条</span></div>
    <p className="auction-disclosure">列表按拍卖轮次展示，同一房产可能有多条记录；地图按小区汇总历史成交房源。来源：来拍辅助数据，未核验付款或过户，不代表区域全量。</p>
    <p className="auction-meta">采集更新 {date(data.last_run?.finished_at)} · {data.last_run?.complete ? '当次列表遍历完成' : '采集范围尚未完整遍历'}</p>
    {!data.records.length && <div className="auction-empty">{data.overall_total ? '当前筛选无结果' : '暂无法拍记录'}</div>}
    <div className="auction-list-records">{data.records.map(record => {
      const deal = record.status === 'done' && record.deal_price_yuan != null && record.deal_price_yuan > 0;
      return <article className="auction-list-card" key={`${record.source}-${record.auction_id}`}>
        <div className="auction-record-heading"><h3>{record.title}</h3><span className={`auction-status ${deal ? 'auction-status-done' : ''}`}>{statuses[record.status] ?? '状态未知'}</span></div>
        <p className="auction-meta">{record.address || '地址暂无'} · {record.round ? `${record.round}拍` : '轮次未知'}</p>
        <div className="auction-list-community"><span>{record.community_display_name || '未关联小区'}</span>{record.community_id && <button className="btn btn-secondary" onClick={() => onView(record.community_id!)}>地图查看</button>}</div>
        <div className="auction-list-prices">
          <div><span>起拍价</span><strong>{amount(record.start_price_yuan)}</strong></div>
          <div><span>成交价</span><strong>{deal ? amount(record.deal_price_yuan) : '暂无'}</strong></div>
          <div><span>成交单价</span><strong>{deal && record.deal_unit_price != null ? `${record.deal_unit_price.toLocaleString('zh-CN')} 元/㎡` : '暂无'}</strong></div>
          <div><span>建筑面积</span><strong>{record.area_m2 == null ? '面积未知' : `${record.area_m2}㎡`}</strong></div>
        </div>
        <p className="auction-meta">开拍 {date(record.start_at)} · 结束 {date(record.end_at)}</p>
        <details><summary>查看房源事实与来源</summary><dl className="auction-facts">
          <div><dt>评估价</dt><dd>{amount(record.appraisal_price_yuan)}</dd></div>
          <div><dt>来源小区名</dt><dd>{record.community_name || '暂无'}</dd></div>
          {Object.entries(riskLabels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{record.risk_notes?.[key] || '未知'}</dd></div>)}
          {record.status === 'unknown' && <div><dt>来源状态</dt><dd>{record.source_status || '未知'}</dd></div>}
        </dl><p className="auction-meta">采集 {date(record.captured_at)} · 记录 {record.auction_id}</p><div className="auction-links"><SafeLink url={record.source_url}>来源记录</SafeLink><SafeLink url={record.original_url}>原始拍卖页面</SafeLink></div></details>
      </article>;
    })}</div>
  </>;
}

export default function AuctionDataList({ refreshVersion, onView, onChanged }: { refreshVersion: number; onView: (id: string) => void; onChanged: () => void }) {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [association, setAssociation] = useState('all');
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<{ key: string; data?: AuctionListData; error?: string } | null>(null);
  const key = JSON.stringify([q, status, association, page, refreshVersion, retry]);
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ q, association, page: String(page), page_size: '20' });
    if (status) params.set('status', status);
    const timer = setTimeout(() => {
      fetchAuctionData<AuctionListData>(`auctions?${params}`, controller.signal)
        .then(data => { if (!controller.signal.aborted) {
          if (page > 1 && !data.records.length) { setPage(Math.max(1, Math.ceil(data.total / 20))); return; }
          setState({ key, data });
        } })
        .catch(() => { if (!controller.signal.aborted) setState({ key, error: '法拍数据暂时不可用' }); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [q, status, association, page, refreshVersion, retry, key]);
  const current = state?.key === key ? state : null;
  return <section className="auction-data-page" aria-label="法拍数据">
    <header className="auction-list-heading"><div><p>滨江住宅 · 法拍记录</p><h2>法拍数据</h2></div><span>逐条看房源，按小区看地图</span></header>
    <div className="auction-list-filters">
      <label>搜索房源<input maxLength={200} placeholder="标题、地址或小区名称" value={q} onChange={e => { setQ(e.target.value); setPage(1); }} /></label>
      <label>拍卖状态<select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">全部状态</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}<option value="unknown">状态未知</option></select></label>
      <label>小区关联<select value={association} onChange={e => { setAssociation(e.target.value); setPage(1); }}><option value="all">全部记录</option><option value="matched">已关联小区</option><option value="unmatched">未关联小区</option></select></label>
      <button className="btn btn-secondary" onClick={() => { setQ(''); setStatus(''); setAssociation('all'); setPage(1); }}>清空筛选</button>
      <button className="btn btn-secondary" onClick={() => { setAssociation('unmatched'); setPage(1); }}>手工待关联</button>
    </div>
    {association === 'unmatched' && <AuctionPendingAssociations refreshVersion={refreshVersion} onChanged={onChanged} />}
    {!current && <p className="auction-empty" role="status">正在加载法拍记录…</p>}
    {current?.error && <div className="auction-empty" role="alert">{current.error} <button onClick={() => setRetry(v => v + 1)}>重试</button></div>}
    {current?.data && <><AuctionListContent data={current.data} onView={onView} />{current.data.total > 20 && <nav className="auction-pagination" aria-label="法拍记录分页"><button disabled={page === 1} onClick={() => setPage(v => v - 1)}>上一页</button><span>{page} / {Math.ceil(current.data.total / 20)}</span><button disabled={page * 20 >= current.data.total} onClick={() => setPage(v => v + 1)}>下一页</button></nav>}</>}
  </section>;
}
