'use client';

import { date, SafeLink, statuses } from './CommunityAuctionHistory';

export const rentalCoverageLabels = {
  data: '有数据', pending: '待采集', unmapped: '待关联来源',
  source_missing: '未找到来源', no_samples: '暂无样本', failed: '采集失败',
};
export type CatalogCoverage = {
  auction: { property_count: number; round_count: number; unidentified_round_count: number };
  rental: { state: keyof typeof rentalCoverageLabels; sample_count: number; captured_at?: string | null;
    stale?: boolean; update_failed?: boolean; error?: string | null };
};
export type CatalogAuctionRecord = { source: string; auction_id: string; asset_id?: string | null;
  title?: string; round?: number | null; status?: string; source_url?: string | null; end_at?: string | null };

export function AuctionCoverage({ value, onView }: { value?: CatalogCoverage['auction']; onView: () => void }) {
  if (!value) return <span className="directory-muted">状态未知</span>;
  if (!value.round_count) return <span className="directory-muted">暂无记录</span>;
  return <div className="catalog-coverage"><button className="catalog-data-link" onClick={onView}
    title={`查看已关联法拍，共${value.round_count}条拍卖轮次；同一房产不重复计套数`}>
    {value.property_count ? `${value.property_count}套` : `${value.unidentified_round_count}轮记录`}
  </button>{value.unidentified_round_count > 0 && <small className="catalog-data-note">
    {value.property_count ? `另${value.unidentified_round_count}轮无法去重` : '缺房产身份，无法去重'}
  </small>}</div>;
}

export function RentalCoverage({ value, showTip = true }: { value?: CatalogCoverage['rental']; showTip?: boolean }) {
  if (!value) return <span className="directory-muted">状态未知</span>;
  const label = rentalCoverageLabels[value.state] || '状态未知';
  const title = [value.captured_at && `采集时间：${date(value.captured_at)}（北京时间）`,
    value.stale && '采集超过30天或日期无效', value.error].filter(Boolean).join('；');
  return <div className="catalog-coverage" title={showTip ? title || undefined : undefined}>
    <span className={value.state === 'data' ? 'catalog-data-value' : value.state === 'failed' || value.state === 'unmapped' ? 'catalog-data-note' : 'directory-muted'}>
      {value.state === 'data' ? `${label} · ${value.sample_count}条` : label}
    </span>{(value.stale || value.update_failed && value.state === 'data') && <small className="catalog-data-note">
      {[value.stale && '数据较旧', value.update_failed && value.state === 'data' && '更新失败'].filter(Boolean).join(' · ')}
    </small>}
  </div>;
}

export function CatalogAuctionRecords({ coverage, records }: { coverage?: CatalogCoverage; records?: CatalogAuctionRecord[] }) {
  if (!coverage) return null;
  const value = coverage.auction;
  if (!value.round_count) return null;
  return <section className="catalog-auction-records" aria-label="关联法拍记录">
    <h4>法拍数据</h4>
    <p className="directory-muted">{value.property_count}套已识别房产 · {value.round_count}条拍卖轮次{value.unidentified_round_count > 0 && ` · ${value.unidentified_round_count}轮缺房产身份，无法跨轮次去重`}</p>
    {!records ? <p role="status">加载法拍记录…</p> :
      <ul className="catalog-auction-list">{records.map(record => <li key={`${record.source}-${record.auction_id}`}>
        <strong>{record.title || `拍卖记录 ${record.auction_id}`}</strong>
        <small>{statuses[record.status || ''] || '状态未知'} · {record.round ? `${record.round}拍` : '轮次未知'}
          {!record.asset_id && ' · 无法跨轮次去重'}</small>
        <SafeLink url={record.source_url}>查看来源记录</SafeLink>
      </li>)}</ul>}
  </section>;
}

export function CatalogRentalDetails({ value }: { value?: CatalogCoverage['rental'] }) {
  if (!value) return null;
  return <section className="catalog-rental-details" aria-label="租金覆盖信息">
    <h4>租金信息</h4><RentalCoverage value={value} showTip={false} />
    {value.captured_at && <p className="directory-muted">采集时间：{date(value.captured_at)}（北京时间）</p>}
    {value.state === 'data' && value.sample_count < 3 && <p className="directory-muted">有效样本不足3条，仅供查看明细，暂不形成租金参考。</p>}
    {value.error && <p className="directory-warning">{value.error}</p>}
  </section>;
}
