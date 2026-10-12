'use client';

import { useEffect, useState } from 'react';
import { fetchAuctionData, type AuctionHistory } from '../../lib/auction-types';
import { date } from './CommunityAuctionHistory';

export function LatestAuctionCardContent({ data, loading, error }: { data?: AuctionHistory; loading?: boolean; error?: boolean }) {
  const latest = data?.available ? data.records[0] : undefined;
  const price = latest?.deal_unit_price;
  const value = price != null ? `${(price / 10000).toFixed(2)}万` : '—';
  const note = loading ? '加载中…' : error ? '暂时不可用' : !data?.available ? '尚未采集' : !latest ? '暂无成交' : `${date(latest.end_at)} · ${latest.area_m2 == null ? '面积未知' : `${latest.area_m2}㎡`}`;
  return <div className="stat-cell latest-auction-card" aria-label="最近法拍成交" title="已采集记录中最近一套的成交单价，来源标记成交，未核验付款或过户">
    <div className="stat-label">最近法拍成交</div>
    <div className="stat-value">{value}<span className="latest-auction-unit">{price != null ? '/㎡' : ''}</span></div>
    <div className="latest-auction-note" role={error ? 'status' : undefined}>{note}</div>
  </div>;
}

export default function LatestAuctionCard({ communityId, refreshVersion }: { communityId: string; refreshVersion: number }) {
  const [state, setState] = useState<{ key: string; data?: AuctionHistory; error?: boolean } | null>(null);
  const key = `${communityId}/${refreshVersion}`;
  useEffect(() => {
    const controller = new AbortController();
    fetchAuctionData<AuctionHistory>(`communities/${encodeURIComponent(communityId)}/auction-history?period=all&area_band=all&page=1&page_size=1`, controller.signal)
      .then(data => { if (!controller.signal.aborted) setState({ key, data }); })
      .catch(() => { if (!controller.signal.aborted) setState({ key, error: true }); });
    return () => controller.abort();
  }, [communityId, refreshVersion, key]);
  const current = state?.key === key ? state : null;
  return <LatestAuctionCardContent data={current?.data} loading={!current} error={current?.error} />;
}
