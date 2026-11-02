'use client';

import { useRentalData } from '../../lib/use-rental-data';
import type { RentalDetailData } from '../../lib/rental-types';

export function CommunityRentalMetricsContent({ data, loading, error }: {
  data?: RentalDetailData; loading?: boolean; error?: string;
}) {
  // 与看板默认口径一致：90–144㎡、全部房型合并重算，不能平均各户型收益率。
  const group = data?.groups.find(item => item.area_band === '90to144' && item.bedrooms === null);
  const estimate = data?.availability === 'available' ? group?.yield_estimate : null;
  const reasons = {
    unmapped: '尚未关联租金来源',
    no_samples: '当前口径暂无租金样本',
    insufficient_samples: '当前口径有效样本不足3套',
    stale: '租金数据超过30天未更新',
    source_failed: '租金采集失败',
    available: '缺少有效售价或租金参考',
  };
  const sale = group?.sale_reference;
  const basis = sale?.price_kind === 'signed' ? '近期签约价' : sale?.price_kind === 'listing' ? '挂牌价' : '售价';
  const note = loading ? '加载中' : error ? '租金数据暂不可用' : estimate
    ? `${group?.sample_count ?? 0}套样本；${basis}${sale?.price_date ? `（${sale.price_date}）` : ''}；租金采集日期${data?.captured_at ?? '未知'}。小区均价与租金样本并非同套房，未扣除空置、税费及维护成本。`
    : data ? reasons[data.availability] : '暂无租金参考';
  const title = `90–144㎡（不含144）、全部房型；${note}`;
  return <>
    <div className="stat-cell" title={title} aria-label="月租售比">
      <div className="stat-label">月租售比</div>
      <div className="stat-value">{estimate?.rent_to_sale_ratio != null ? `1:${Math.round(estimate.rent_to_sale_ratio)}` : '—'}</div>
    </div>
    <div className="stat-cell" title={title} aria-label="年化毛收益率">
      <div className="stat-label">年化毛收益率</div>
      <div className="stat-value">{estimate?.annualized_gross_yield_pct != null ? `${estimate.annualized_gross_yield_pct.toFixed(2)}%` : '—'}</div>
    </div>
  </>;
}

export default function CommunityRentalMetrics({ communityId }: { communityId: string }) {
  const { data, loading, error } = useRentalData(communityId, {
    areaBand: '90to144', bedrooms: 'all', page: 1, view: 'valid',
  });
  return <CommunityRentalMetricsContent data={data} loading={loading} error={error} />;
}
