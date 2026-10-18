'use client';

import { useState } from 'react';
import { useRentalData } from '../../lib/use-rental-data';
import { RentalSourceAssociation } from '../rental/RentalSourceManager';
import {
  RENTAL_DETAIL_PAGE_SIZE,
  type RentalAreaBand,
  type RentalBedroomsFilter,
  type RentalDetailData,
  type RentalDetailSample,
  type RentalGroup,
  type RentalSampleView,
} from '../../lib/rental-types';

const areaBandLabels: Record<string, string> = {
  lt90: '90㎡以下',
  '90to144': '90–144㎡（不含144）',
  gte144: '144㎡及以上',
};

/** 来源链接只允许预期 https 来源域（zu.fang.com） */
function RentalSourceLink({ url, children }: { url?: string | null; children: React.ReactNode }) {
  let safe = false;
  try {
    const parsed = url ? new URL(url) : null;
    safe = Boolean(parsed && parsed.protocol === 'https:' && parsed.hostname === 'zu.fang.com');
  } catch { safe = false; }
  return safe && url ? <a href={url} target="_blank" rel="noopener noreferrer">{children} ↗</a> : null;
}

function date(value?: string | null) {
  if (!value) return '未知';
  const parsed = new Date(value.includes('T') ? value : `${value.replace(' ', 'T')}${value.length > 10 ? '+08:00' : 'T00:00:00+08:00'}`);
  return Number.isNaN(parsed.getTime()) ? '未知' : parsed.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
}
function fmtMonthRent(value: number | null) { return value == null ? '暂无' : `${Math.round(value).toLocaleString()} 元/月`; }
function fmtUnitRent(value: number | null) { return value == null ? '暂无' : `${value.toFixed(1)} 元/㎡/月`; }
function fmtYieldPct(value: number | null) { return value == null ? '—' : `约 ${value.toFixed(2)}%`; }
function fmtRentToSale(value: number | null) { return value == null ? '—' : `1 : ${Math.round(value)}`; }

const priceKindLabels: Record<string, string> = { signed: '近期签约价', listing: '挂牌价' };

function bedroomsLabel(bedrooms: number | null) { return bedrooms == null ? '全部房型合并重算' : `${bedrooms} 居室`; }

function bedroomsSummary(distribution: Record<string, number>): string {
  const entries = Object.entries(distribution);
  if (!entries.length) return '暂无房型分布';
  return entries.map(([bedrooms, count]) => `${bedrooms === 'null' ? '未知' : `${bedrooms}居`}×${count}`).join('、');
}

function GroupCard({ group }: { group: RentalGroup }) {
  const rent = group.rent_reference;
  const sale = group.sale_reference;
  const yieldEstimate = group.yield_estimate;
  return <article className="rental-group">
    <div className="rental-group-heading">
      <h4>{bedroomsLabel(group.bedrooms)} · {areaBandLabels[group.area_band] ?? group.area_band}</h4>
      <span>{group.sample_count} 套合格样本</span>
    </div>
    {rent ? <>
      <div className="rental-group-metrics">
        <div><span>月租中位数</span><strong>{fmtMonthRent(rent.median_month_rent_yuan)}</strong></div>
        <div><span>单位租金中位数</span><strong>{fmtUnitRent(rent.median_unit_rent_yuan_m2_month)}</strong></div>
        <div><span>P25–P75</span><strong>{rent.p25_unit_rent_yuan_m2_month == null || rent.p75_unit_rent_yuan_m2_month == null ? '—' : `${rent.p25_unit_rent_yuan_m2_month.toFixed(1)} ~ ${rent.p75_unit_rent_yuan_m2_month.toFixed(1)}`}</strong></div>
      </div>
      {yieldEstimate && <div className="rental-yield">
        <div><span>参考年化毛收益率</span><strong>{fmtYieldPct(yieldEstimate.annualized_gross_yield_pct)}</strong></div>
        <div><span>月租售比</span><strong>{fmtRentToSale(yieldEstimate.rent_to_sale_ratio)}</strong></div>
        {sale && <p className="rental-meta">售价口径：{priceKindLabels[sale.price_kind ?? ''] ?? '口径未知'}{sale.price_date ? `（价格日期 ${date(sale.price_date)}）` : ''} · 单价 {sale.unit_price_yuan_m2 == null ? '未知' : `${Math.round(sale.unit_price_yuan_m2).toLocaleString()} 元/㎡`}</p>}
      </div>}
    </> : <p className="rental-meta">样本不足 3 条，仅展示明细，不输出该组租金参考。</p>}
  </article>;
}

function SampleItem({ sample, excluded }: { sample: RentalDetailSample; excluded: boolean }) {
  return <li className="rental-sample">
    <div className="rental-sample-main">
      <span className="rental-sample-rent">{fmtMonthRent(sample.month_rent_yuan)}</span>
      <span>{sample.area_m2 == null ? '面积未知' : `${sample.area_m2}㎡`}</span>
      <span>{sample.bedrooms == null ? '户型未知' : `${sample.bedrooms}居`}</span>
      <span>{sample.unit_rent_yuan_m2_month == null ? '单价未知' : `${sample.unit_rent_yuan_m2_month.toFixed(1)} 元/㎡/月`}</span>
    </div>
    {sample.title && <p className="rental-meta">{sample.title}</p>}
    {excluded && <p className="rental-exclude-reason">排除理由：{sample.exclude_reason || '未知'}</p>}
    <p className="rental-meta">采集 {date(sample.captured_at)} · <RentalSourceLink url={sample.source_url}>来源房源</RentalSourceLink></p>
  </li>;
}

export function RentalReferenceContent({ data, view = 'valid' }: { data: RentalDetailData; view?: RentalSampleView }) {
  if (data.availability === 'unmapped') {
    return <div className="rental-empty">这个小区尚未关联租金来源，请在上方查找并确认对应小区。</div>;
  }
  if (data.availability === 'no_samples') {
    return <div className="rental-empty">{data.captured_at ? '已关联来源，但当前筛选下没有可用房源样本。' : '已关联来源，尚未采集租金。在“采集任务”里开始“采集租金”即可更新。'}</div>;
  }
  if (data.availability === 'source_failed' && data.groups.length === 0) {
    return <div className="rental-empty">最近一次租金采集失败，暂无可展示数据。</div>;
  }

  const notices: string[] = [];
  if (data.regional_sample) notices.push('来自区域采集的租房样本，尚未覆盖该小区全部房源；关联后按已保存样本计算参考。');
  if (data.availability === 'insufficient_samples') {
    notices.push('有效样本不足 3 条，仅展示明细，不输出租金参考与收益估算。');
  }
  if (data.availability === 'stale') {
    notices.push('租金数据已超过 30 天未更新：明细仍可查看，收益率估算已停用，也不参与收益率排序。');
  }
  if (data.last_refresh?.status === 'failed') {
    notices.push(`最近一次租金更新失败（${data.last_refresh.error || '原因未知'}），以下为最近一次成功采集的历史数据。`);
  }

  const showYieldDisclosure = data.groups.some(group => group.yield_estimate != null);
  const showingExcluded = view === 'excluded';

  return <>
    {notices.map(notice => <p key={notice} className="rental-note" role="status">{notice}</p>)}
    {showYieldDisclosure && <p className="rental-note rental-note-warning">粗略估算——小区均价与租金组并非同户型成交，收益率仅供数量级参考，不代表真实市场收益。</p>}

    {data.groups.length > 0 && <section className="rental-groups" aria-label="租金分组参考">
      {data.groups.map(group => <GroupCard key={`${group.bedrooms ?? 'all'}-${group.area_band}`} group={group} />)}
    </section>}

    <p className="rental-meta">房型分布：{bedroomsSummary(data.bedrooms_distribution)}</p>

    <section className="rental-samples" aria-label="租金样本明细">
      <h4 className="rental-samples-heading">{showingExcluded ? `已排除样本（${data.excluded_count}）` : `有效候选样本（${data.sample_count}）`}</h4>
      {data.samples.length
        ? <ul className="rental-sample-list">{data.samples.map(sample => <SampleItem key={sample.source_listing_id} sample={sample} excluded={showingExcluded} />)}</ul>
        : <div className="rental-empty">{showingExcluded ? '没有已排除样本' : '当前筛选下暂无有效候选样本'}</div>}
    </section>

    <p className="rental-meta">租金采集日期 {date(data.captured_at)}{data.source_links.length ? ' · ' : ''}{data.source_links.map((link, index) => <RentalSourceLink key={link} url={link}>来源{index + 1}</RentalSourceLink>)}</p>
  </>;
}

export default function CommunityRentalReference({ communityId }: { communityId: string }) {
  const [areaBand, setAreaBand] = useState<RentalAreaBand>('all');
  const [bedrooms, setBedrooms] = useState<RentalBedroomsFilter>('all');
  const [view, setView] = useState<RentalSampleView>('valid');
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const { data, error } = useRentalData(communityId, { areaBand, bedrooms, page, view }, retry);
  const showingExcluded = view === 'excluded';

  return <section className="rental-reference" aria-label="小区租金与收益参考">
    <div className="rental-filters">
      <label>面积段<select value={areaBand} onChange={e => { setAreaBand(e.target.value as RentalAreaBand); setPage(1); }}>
        <option value="all">全部面积</option>
        <option value="lt90">90㎡以下</option>
        <option value="90to144">90–144㎡（不含144）</option>
        <option value="gte144">144㎡及以上</option>
      </select></label>
      <label>房型<select value={bedrooms} onChange={e => { setBedrooms(e.target.value as RentalBedroomsFilter); setPage(1); }}>
        <option value="all">全部房型</option>
        <option value="1">1居</option>
        <option value="2">2居</option>
        <option value="3">3居</option>
        <option value="4plus">4居及以上</option>
      </select></label>
    </div>
    <RentalSourceAssociation key={communityId} communityId={communityId} />
    <p className="rental-meta">采集在“采集任务”里进行，“采集租金”会更新全部已关联小区。</p>
    {!data && !error && <p className="rental-empty" role="status">正在加载租金数据…</p>}
    {error && <div className="rental-empty" role="alert">{error} <button onClick={() => setRetry(v => v + 1)}>重试</button></div>}
    {data && <RentalReferenceContent data={data} view={view} />}
    {data && <div className="rental-view-switch" role="group" aria-label="样本视图">
      <button aria-pressed={!showingExcluded} onClick={() => { setView('valid'); setPage(1); }}>有效候选</button>
      <button aria-pressed={showingExcluded} onClick={() => { setView('excluded'); setPage(1); }}>已排除{data.excluded_count ? `（${data.excluded_count}）` : ''}</button>
    </div>}
    {data && data.total > RENTAL_DETAIL_PAGE_SIZE && <nav className="rental-pagination" aria-label="租金样本分页">
      <button disabled={page === 1} onClick={() => setPage(v => v - 1)}>上一页</button>
      <span>{page} / {Math.ceil(data.total / RENTAL_DETAIL_PAGE_SIZE)}</span>
      <button disabled={page * RENTAL_DETAIL_PAGE_SIZE >= data.total} onClick={() => setPage(v => v + 1)}>下一页</button>
    </nav>}
  </section>;
}
