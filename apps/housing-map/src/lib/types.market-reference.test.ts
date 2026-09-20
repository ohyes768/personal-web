import { isListingReference, type MarketReference } from './types';

const unavailable: MarketReference = { available: false, reason: 'invalid_snapshot' };
const listingReference: MarketReference = {
  available: true,
  source: {
    name: '安居客',
    url: 'https://m.anjuke.com/hz/trendency/binjiangb/',
    captured_at: '2026-09-19',
  },
  scope: '滨江区',
  price_kind: 'listing_reference',
  overall: { avg_price: 38323, mom_percent: 0.41, yoy_percent: 3.6 },
  subdistricts: [],
};

// 编译期契约：无效快照不可通过守卫，挂牌参考快照可作为页面数据源。
void isListingReference(unavailable);
void isListingReference(listingReference);
