'use client';

import type { Community } from '../../lib/types';
import {
  monthLabel,
  normalizePriceBlock,
  dualPriceLines,
  refreshStatusLine,
  shortDate,
  STALE_HINT,
  type NormalizedPriceBlock,
  type NormalizedPriceEntry,
} from '../../lib/price-freshness';

// 签约/挂牌格的提示行: 签约格是「所属月份 + 采集日」两行, 挂牌格只有采集日
// (挂牌价没有成交月份概念, 不编造)。缺失时如实说明, 不拿采集日顶替月份。
function priceMeta(entry: NormalizedPriceEntry | null, tag: '签' | '挂'): string[] {
  if (entry == null) return [tag === '签' ? '无有效签约价' : '无有效挂牌价'];
  const lines: string[] = [];
  if (tag === '签') lines.push(`${monthLabel(entry.month) ?? '月份未知'}签约`);
  lines.push(entry.capturedDate ? `${entry.capturedDate}采集` : '采集时间未知');
  return lines;
}

function countsTitle(counts: NormalizedPriceBlock['counts']): string {
  return counts.capturedAt
    ? `在售套数与近月签约为同一快照的套数；套数采集 ${shortDate(counts.capturedAt) ?? counts.capturedAt}`
    : '在售套数与近月签约为同一快照的套数；套数无独立采集时间';
}

// 小区弹窗的价格块 (R1/R2): 签约/挂牌各自展示价格、所属月份、采集日、陈旧提示;
// 过期签约放历史参考区, 不与当前价混排; 无有效当前价显示"暂无近期价格",
// 历史与套数照常展示。套数带自己的采集时间, 不冒充价格更新 (R3)。
export default function PriceDetails({ price }: { price: Community['price'] }) {
  const block = normalizePriceBlock(price);
  const lines = dualPriceLines(block);

  // 提示行: 可见文本保留页面必须可分辨的事实, 更细口径放各格悬浮说明
  const notes: string[] = [];
  if (!block.hasCurrentPrice) notes.push('暂无近期价格');
  const staleParts: string[] = [];
  if (block.deal?.stale) staleParts.push(`签约价${STALE_HINT}`);
  if (block.listing?.stale) staleParts.push(`挂牌价${STALE_HINT}`);
  if (staleParts.length) notes.push(staleParts.join(' · '));
  if (block.historyDeal) {
    const month = monthLabel(block.historyDeal.month);
    notes.push(
      `历史参考 ${month ?? '月份未知'}签约均价 ${block.historyDeal.price.toLocaleString()} 元/㎡`
      + `（${block.historyDeal.capturedDate ?? '采集时间未知'}采集）`
      + ' · 超过6个月，不参与当前比价',
    );
  }
  const status = refreshStatusLine(block.refresh);
  if (status) notes.push(status);

  const counts = block.counts;
  const countsMeta = counts.capturedAt
    ? `套数采集 ${shortDate(counts.capturedAt) ?? counts.capturedAt}`
    : null;

  const priceCell = (tag: '签' | '挂', entry: NormalizedPriceEntry | null) => (
    <div key={tag} className="stat-cell" title={lines.find(line => line.tag === tag)?.title}>
      <div className="stat-label">{tag === '签' ? '签约均价' : '挂牌均价'}</div>
      <div className="stat-value">
        {entry == null ? '—' : entry.price.toLocaleString()}
        {entry?.stale && <span className="price-stale-dot" aria-label={STALE_HINT}>!</span>}
      </div>
      <div className="stat-meta">
        {priceMeta(entry, tag).map(text => <div key={text}>{text}</div>)}
      </div>
    </div>
  );

  return (
    <>
      {priceCell('签', block.deal)}
      {priceCell('挂', block.listing)}
      <div className="stat-cell" title={countsTitle(counts)}>
        <div className="stat-label">在售套数</div>
        <div className="stat-value">{counts.listingCount ?? '-'}</div>
        <div className="stat-meta">{countsMeta ?? '套数无采集时间'}</div>
      </div>
      <div className="stat-cell" title={countsTitle(counts)}>
        <div className="stat-label">近月签约</div>
        <div className="stat-value">{counts.dealCount ?? '-'}</div>
        <div className="stat-meta">{countsMeta ?? '套数无采集时间'}</div>
      </div>
      {notes.length > 0 && (
        <div className="price-detail-notes" style={{ gridColumn: '1 / -1' }}>
          {notes.map((note, index) => <div key={index}>{note}</div>)}
        </div>
      )}
    </>
  );
}
