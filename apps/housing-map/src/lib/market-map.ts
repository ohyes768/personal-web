// 地图「二手房 / 新房 / 全部」切换与「附近二手房」比较的纯函数。
//
// 这些规则集中在一层, 供地图图层、可见计数、详情弹框与单元测试共用：
// 判定口径只在这里写一次, 避免各处各写一套导致列表、统计与详情互相打架。

import { getDisplayPrice } from './types';
import type { Community, MarketState } from './types';

// 地图切换的三种视角; 'all' 是默认值, 保证未知房源类型不会被悄悄藏起来
export type MarketMode = 'second_hand' | 'new_house' | 'all';

// 二手房价格口径: 混合 / 仅签约 / 仅挂牌 (与页面上的价格口径开关一致)
export type PriceMode = 'all' | 'deal' | 'listing';

// 切换项的展示文案; 顺序即按钮顺序, 「全部」放最后便于逐级收窄
export const MARKET_MODE_OPTIONS: { value: MarketMode; label: string }[] = [
  { value: 'second_hand', label: '二手房' },
  { value: 'new_house', label: '新房' },
  { value: 'all', label: '全部' },
];

// 房源类型的对外文案; 未知必须显式说明「待核实」, 不能默认成二手房
export const MARKET_STATE_LABELS: Record<MarketState, string> = {
  new_house: '新房项目',
  second_hand: '二手房',
  unknown: '房源类型待核实',
};

// 就近比较的默认半径 (米, 直线距离); 取 1.5 公里覆盖步行 15~20 分钟的可比范围
export const NEARBY_DEFAULT_RADIUS_METERS = 1500;

// 无价时的统一占位文案
export const NO_PRICE_TEXT = '暂无价格';

// 新房暂无可信价格来源时的占位文案;
// 二手房快照与新房项目价格口径不同, 新房不得借用二手价格, 所以这里恒为占位
export const NEW_HOUSE_PRICE_PLACEHOLDER = NO_PRICE_TEXT;

// 就近比较的返回项: 小区本体 + 到锚点的直线距离 (整数米)
export interface NearbySecondHand {
  community: Community;
  distance: number;
}

/**
 * 取小区的房源类型。
 * 字段缺失或取值非法一律落到 unknown —— 未知必须显式呈现,
 * 默认成二手房会让统计、图层与详情把没核实过的小区悄悄算进二手口径。
 */
export function marketStateOf(community: Community): MarketState {
  const state = community.market_state;
  if (state === 'new_house' || state === 'second_hand' || state === 'unknown') return state;
  return 'unknown';
}

// 是否为二手房: 用于把均价、套数、市场行情等二手专属聚合显式限定在二手
export function isSecondHand(community: Community): boolean {
  return marketStateOf(community) === 'second_hand';
}

// 是否为新房项目
export function isNewHouse(community: Community): boolean {
  return marketStateOf(community) === 'new_house';
}

/**
 * 按当前切换态挑出地图上可见的小区。
 * unknown 只在「全部」里出现: 单独切到二手房或新房时,
 * 未核实类型不该被塞进其中一侧, 也不该凭空消失而不给理由。
 * 返回新数组, 不改动入参。
 */
export function visibleCommunities(communities: Community[], mode: MarketMode): Community[] {
  if (mode === 'all') return communities.slice();
  const wanted: MarketState = mode === 'new_house' ? 'new_house' : 'second_hand';
  return communities.filter(community => marketStateOf(community) === wanted);
}

/**
 * 地理直线距离 (米), haversine 公式。
 * 不用经纬度度数直接相减 —— 那样在杭州一带误差可达数百米;
 * 也不冒充步行距离, 实际步行路径通常明显更长。
 */
export function haversineMeters(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
): number {
  const EARTH_RADIUS_METERS = 6371000;
  const toRad = (deg: number): number => (deg * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const lat1 = toRad(a.latitude);
  const lat2 = toRad(b.latitude);
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon;
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * 锚点附近半径内的二手房列表。
 * - 只收二手房: 新房与未知房源类型不参与二手比较, 避免口径混杂
 * - 无价二手照样入选: 没有价格只是缺一个字段, 位置仍然可比
 * - 排序稳定: 距离升序, 距离相同按 community_id 升序, 便于测试与人工核对
 */
export function nearbySecondHand(
  anchor: Community,
  communities: Community[],
  options?: { radiusMeters?: number; limit?: number },
): NearbySecondHand[] {
  const radiusMeters = options?.radiusMeters ?? NEARBY_DEFAULT_RADIUS_METERS;
  if (!Number.isFinite(anchor.latitude) || !Number.isFinite(anchor.longitude)) return [];

  const found: NearbySecondHand[] = [];
  for (const community of communities) {
    if (community.community_id === anchor.community_id) continue; // 锚点自身不入列
    if (!isSecondHand(community)) continue;
    if (!Number.isFinite(community.latitude) || !Number.isFinite(community.longitude)) continue;
    const exact = haversineMeters(anchor, community);
    // 边界含等号: 半径算作闭区间, 1e-6 的容差只用来吸收浮点误差
    if (exact > radiusMeters + 1e-6) continue;
    found.push({ community, distance: Math.round(exact) });
  }

  found.sort((a, b) => (a.distance !== b.distance
    ? a.distance - b.distance
    : a.community.community_id.localeCompare(b.community.community_id)));

  return options?.limit != null ? found.slice(0, options.limit) : found;
}

/**
 * 新房价格文案。
 * 新房价格必须有明确口径的可信来源 (备案/参考均价) 才能展示,
 * 目前没有这条数据链路, 因此恒为占位文案, 绝不取用二手价格字段。
 */
export function newHousePriceText(community: Community, priceMode: PriceMode): string {
  void community;
  void priceMode;
  return NEW_HOUSE_PRICE_PLACEHOLDER;
}

// 新房是否已有可信价格来源; 目前恒为否, 供调用方决定是否渲染价格区块
export function hasTrustedNewHousePrice(community: Community): boolean {
  void community;
  return false;
}

/**
 * 二手房价格文案 (元/㎡)。
 * 口径沿用页面既有约定: 'all' 优先签约均价、无则挂牌均价; 无价时显示占位。
 */
export function secondHandPriceText(community: Community, priceMode: PriceMode): string {
  const value = priceMode === 'deal'
    ? community.price.deal_avg_price
    : priceMode === 'listing'
      ? community.price.listing_avg_price
      : getDisplayPrice(community.price);
  if (value == null) return NO_PRICE_TEXT;
  const label = priceMode === 'deal'
    ? '签约均价'
    : priceMode === 'listing'
      ? '挂牌均价'
      : community.price.deal_avg_price != null ? '签约均价' : '挂牌均价';
  return `${value.toLocaleString()} 元/㎡（${label}）`;
}
