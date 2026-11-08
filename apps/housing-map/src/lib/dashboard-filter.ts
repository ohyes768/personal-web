// 数据看板的筛选与统计口径 (纯函数, 可单测)。
//
// 房源类型判定复用 lib/market-map.ts 的 marketStateOf —— 看板与地图必须共用
// 同一套「什么算新房 / 二手房 / 待核实」的规则, 否则看板上的计数会和地图图层对不上。
// 二手专属聚合 (均价、签约套数、有价小区) 同样只统计二手房, 不把新房或待核实
// 小区混进二手口径。

import { getDisplayPrice } from './types';
import type { Community } from './types';
import { marketStateOf } from './market-map';
import { normalizePriceBlock } from './price-freshness';

// 看板的房源类型筛选值: 三个显式房源类型 + 全部
export type DashMarketFilter = 'all' | 'second_hand' | 'new_house' | 'unknown';

// 下拉选项文案 (顺序即展示顺序)
export const DASH_MARKET_FILTER_OPTIONS: { value: DashMarketFilter; label: string }[] = [
  { value: 'all', label: '全部房源' },
  { value: 'second_hand', label: '二手房' },
  { value: 'new_house', label: '新房项目' },
  { value: 'unknown', label: '房源类型待核实' },
];

// 价格区间的取值集合 (值本身即区间边界, 保持与页面既有口径一致)
export const DASH_PRICE_RANGES = ['0-20000', '20000-35000', '35000-50000', '50000-999999'] as const;
export type DashPriceRange = typeof DASH_PRICE_RANGES[number] | '';

// 评分区间的取值集合
export const DASH_SCORE_RANGES = ['80-100', '60-80', '0-60'] as const;
export type DashScoreRange = typeof DASH_SCORE_RANGES[number] | '';

/**
 * 小区是否落在指定房源类型筛选内。
 * 'all' 放行全部, 其余按显式 market_state 精确匹配;
 * 待核实不是任何一种已核实类型, 只有选它自己时才单独成列。
 */
export function matchesDashMarket(community: Community, filter: DashMarketFilter): boolean {
  if (filter === 'all') return true;
  return marketStateOf(community) === filter;
}

/**
 * 看板筛选条件。空字符串表示"不限"。
 */
export interface DashFilterState {
  searchQuery: string;
  subdistrict: string;
  priceRange: DashPriceRange;
  scoreRange: DashScoreRange;
  market: DashMarketFilter;
}

/**
 * 按看板筛选条件过滤小区。
 *
 * 价格口径说明: 取显示价 (签约优先, 无则挂牌), 无价小区按 0 处理。
 * 价格区间的四档是互斥的完整划分 —— 低于 2 万的一档只收「有价且低于 2 万」,
 * 无价(0)的小区在任何价格档里都不匹配, 新房因为没有可信价格同样不匹配。
 */
export function filterDashboardCommunities(
  communities: Community[],
  filters: DashFilterState,
): Community[] {
  const query = filters.searchQuery.trim().toLowerCase();
  return communities.filter(c => {
    if (!matchesDashMarket(c, filters.market)) return false;
    if (filters.subdistrict && c.subdistrict !== filters.subdistrict) return false;
    if (filters.priceRange) {
      const price = getDisplayPrice(c.price) ?? 0;
      if (filters.priceRange === '0-20000' && (price <= 0 || price >= 20000)) return false;
      if (filters.priceRange === '20000-35000' && (price < 20000 || price >= 35000)) return false;
      if (filters.priceRange === '35000-50000' && (price < 35000 || price >= 50000)) return false;
      if (filters.priceRange === '50000-999999' && price < 50000) return false;
    }
    if (filters.scoreRange) {
      const score = c.score?.total_score || 0;
      if (filters.scoreRange === '80-100' && score < 80) return false;
      if (filters.scoreRange === '60-80' && (score < 60 || score >= 80)) return false;
      if (filters.scoreRange === '0-60' && score >= 60) return false;
    }
    if (query && !c.community_name.toLowerCase().includes(query)) return false;
    return true;
  });
}

/**
 * 看板统计卡片的数据来源。
 * 均价、签约套数、有价小区是二手专属口径: 只统计二手房, 且均价只对「有价」的
 * 二手房取平均 (无价小区不参与, 免得把 0 当成价格拉低均价)。
 */
export interface DashStats {
  total: number;
  secondHand: number;
  newHouse: number;
  unknown: number;
  avgPrice: number | null;
  dealCount: number;
  withPrice: number;
}

export function dashboardStats(communities: Community[]): DashStats {
  let secondHand = 0;
  let newHouse = 0;
  let unknown = 0;
  let priceSum = 0;
  let pricedCount = 0;
  let dealCount = 0;
  let withPrice = 0;

  for (const c of communities) {
    const state = marketStateOf(c);
    if (state === 'new_house') {
      newHouse++;
      continue;
    }
    if (state !== 'second_hand') {
      unknown++;
      continue;
    }
    secondHand++;
    const price = getDisplayPrice(c.price);
    if (price != null) {
      priceSum += price;
      pricedCount++;
      withPrice++;
    }
    dealCount += normalizePriceBlock(c.price).counts.dealCount || 0;
  }

  return {
    total: communities.length,
    secondHand,
    newHouse,
    unknown,
    avgPrice: pricedCount > 0 ? Math.round(priceSum / pricedCount) : null,
    dealCount,
    withPrice,
  };
}
