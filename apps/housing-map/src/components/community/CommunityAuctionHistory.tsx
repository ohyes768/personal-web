'use client';

import { useEffect, useState } from 'react';
import { fetchAuctionData, type AuctionHistory, type AuctionPeriod, type AuctionAreaBand, type AuctionRecord } from '../../lib/auction-types';

const riskLabels: Record<string, string> = {
  is_empty: '腾空情况', rent_desc: '租赁情况', transfer_desc: '过户情况',
  other_fee_desc: '欠费及其他事实', tax_desc: '税费情况',
};
const areaSources: Record<string, string> = { structured: '结构化建筑面积', investigation_table: '调查表建筑面积', announcement: '公告建筑面积' };
const statuses: Record<string, string> = { done: '来源标记成交', failure: '流拍', todo: '待开拍', doing: '在拍', pause: '暂停', break: '中止', revocation: '撤回', debt: '抵债' };
function date(value?: string | null) {
  if (!value) return '未知';
  const parsed = new Date(value.includes('T') ? value : `${value.replace(' ', 'T')}${value.length > 10 ? '+08:00' : 'T00:00:00+08:00'}`);
  return Number.isNaN(parsed.getTime()) ? '未知' : parsed.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
}
function amount(value?: number | null) { return value == null ? '暂无' : `${(value / 10000).toFixed(2)}万`; }
function SafeLink({ url, children }: { url?: string | null; children: React.ReactNode }) {
  let safe = false;
  try {
    safe = Boolean(url && ['http:', 'https:'].includes(new URL(url).protocol));
  } catch { safe = false; }
  return safe && url ? <a href={url} target="_blank" rel="noopener noreferrer">{children} ↗</a> : null;
}
function DealRecord({ record }: { record: AuctionRecord }) {
  return <article className="auction-record">
    <div className="auction-record-heading"><h4>{record.title}</h4><span>{record.round ? `${record.round}拍` : '轮次未知'}</span></div>
    <div className="auction-record-price"><strong>{amount(record.deal_price_yuan)} <small>成交总价</small></strong><span>{record.deal_unit_price == null ? '单价未知' : `${amount(record.deal_unit_price)}元/㎡`}</span></div>
    <p className="auction-meta">{record.area_m2 == null ? '面积未知' : `${record.area_m2}㎡`} · 拍卖结束 {date(record.end_at)}</p>
    <details><summary>房源事实与拍卖过程</summary>
      <dl className="auction-facts">
        <div><dt>成交总价</dt><dd>{record.deal_price_yuan?.toLocaleString() ?? '未知'} 元</dd></div>
        <div><dt>成交单价</dt><dd>{record.deal_unit_price?.toLocaleString() ?? '未知'} 元/㎡</dd></div>
        <div><dt>面积来源</dt><dd>{areaSources[record.area_source ?? ''] ?? '未知'}</dd></div>
        {Object.entries(riskLabels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{record.risk_notes?.[key] || '未知'}</dd></div>)}
      </dl>
      {record.identity_warning && <p className="auction-note">{record.identity_warning}</p>}
      <ol className="auction-rounds">{record.rounds.map(round => <li key={`${round.source}-${round.auction_id}`}>
        {round.round ? `${round.round}拍` : '轮次未知'} · {statuses[round.status] ?? '状态未知'} · {date(round.end_at)}
        {round.deal_price_yuan ? ` · 成交 ${amount(round.deal_price_yuan)}` : round.start_price_yuan ? ` · 起拍 ${amount(round.start_price_yuan)}` : ''}
      </li>)}</ol>
      <p className="auction-meta">来源：来拍辅助数据 · 抓取 {date(record.captured_at)}</p>
      <div className="auction-links"><SafeLink url={record.source_url}>来源记录</SafeLink><SafeLink url={record.original_url}>原始拍卖页面</SafeLink></div>
    </details>
  </article>;
}
export function AuctionHistoryContent({ data }: { data: AuctionHistory }) {
  if (!data.available) return <div className="auction-empty">尚未采集法拍数据</div>;
  const stats = data.stats;
  return <>
    <div className="auction-stats">
      <div className="auction-median"><span>成交单价中位数</span><strong>{amount(stats.median_unit_price_yuan)}<small>{stats.median_unit_price_yuan == null ? '' : '元/㎡'}</small></strong></div>
      <div><span>成交房源</span><strong>{stats.deal_property_count}<small>套</small></strong></div>
    </div>
    <p className="auction-meta">有效单价样本 {stats.unit_price_sample_count} 套 · 最新成交 {date(stats.latest_end_at)}</p>
    {stats.min_unit_price_yuan != null && <p className="auction-meta">单价范围 {amount(stats.min_unit_price_yuan)}～{amount(stats.max_unit_price_yuan)}元/㎡</p>}
    {stats.sample_warning && <p className="auction-note">{stats.sample_warning}，请结合具体房源条件判断。</p>}
    <p className="auction-disclosure">来源标记成交，未核验付款或过户。当前已采集记录，不代表区域全量；未知风险不代表无风险。</p>
    <p className="auction-meta">采集更新 {date(data.last_run?.finished_at)} · {data.last_run?.complete ? '当次列表遍历完成' : '采集范围尚未完整遍历'}</p>
    {data.records.length ? data.records.map(record => <DealRecord key={`${record.source}-${record.auction_id}`} record={record} />) : <div className="auction-empty">当前筛选下暂无成交记录</div>}
  </>;
}
export default function CommunityAuctionHistory({ communityId }: { communityId: string }) {
  const [period, setPeriod] = useState<AuctionPeriod>('12m');
  const [area, setArea] = useState<AuctionAreaBand>('all');
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<{ key: string; data?: AuctionHistory; error?: string } | null>(null);
  const key = `${communityId}/${period}/${area}/${page}/${retry}`;
  useEffect(() => {
    const controller = new AbortController();
    fetchAuctionData<AuctionHistory>(`communities/${encodeURIComponent(communityId)}/auction-history?period=${period}&area_band=${area}&page=${page}&page_size=10`, controller.signal)
      .then(data => { if (!controller.signal.aborted) setState({ key, data }); })
      .catch(() => { if (!controller.signal.aborted) setState({ key, error: '法拍数据暂时不可用' }); });
    return () => controller.abort();
  }, [communityId, period, area, page, retry, key]);
  const current = state?.key === key ? state : null;
  return <section className="auction-history" aria-label="小区法拍成交历史">
    <div className="auction-filters">
      <label>成交时间<select value={period} onChange={e => { setPeriod(e.target.value as AuctionPeriod); setPage(1); }}><option value="12m">近12个月</option><option value="24m">近24个月</option><option value="all">全部历史</option></select></label>
      <label>建筑面积<select value={area} onChange={e => { setArea(e.target.value as AuctionAreaBand); setPage(1); }}><option value="all">全部面积</option><option value="lt90">90㎡以下</option><option value="90to144">90–144㎡（不含144）</option><option value="gte144">144㎡及以上</option></select></label>
    </div>
    {!current && <p className="auction-empty" role="status">正在加载成交记录…</p>}
    {current?.error && <div className="auction-empty" role="alert">{current.error} <button onClick={() => setRetry(v => v + 1)}>重试</button></div>}
    {current?.data && <><AuctionHistoryContent data={current.data} />{current.data.total > 10 && <nav className="auction-pagination" aria-label="成交记录分页"><button disabled={page === 1} onClick={() => setPage(v => v - 1)}>上一页</button><span>{page} / {Math.ceil(current.data.total / 10)}</span><button disabled={page * 10 >= current.data.total} onClick={() => setPage(v => v + 1)}>下一页</button></nav>}</>}
  </section>;
}
