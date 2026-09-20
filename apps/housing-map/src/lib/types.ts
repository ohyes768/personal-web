// 小区综合数据
export interface Community {
  community_id: string;
  community_name: string;
  district: string;       // 滨江区
  subdistrict: string;   // 浦沿/长河/西兴
  address: string;
  latitude: number;       // 高德坐标
  longitude: number;
  price: PriceInfo;      // 价格快照
  pois: POI[];           // 周边设施
  score: ScoreResult;    // 综合评分
  property_type?: string; // 物业类型：住宅/写字楼/公寓/商贸/其他
  boundary?: number[][][]; // 小区边界轮廓 (GCJ-02): [环][点][lng,lat]
  boundary_source?: 'shp' | 'osm'; // 轮廓来源: shp=本地Shapefile, osm=OpenStreetMap
  build_year?: number | null;   // 建成年代(透明售房网), null=无数据
  parking_ratio?: number | null;  // 车位比 = 车位数/总户数, null=数据不足
  property_fee?: number | null;   // 物业费 元/㎡/月, null=无数据
  far_ratio?: number | null;      // 容积率, null=无数据
  greening_rate?: number | null;  // 绿化率 %, null=无数据
  nearest_subway?: { name: string; distance: number } | null; // 最近地铁站(直线距离,米)
}

export interface PriceInfo {
  listing_avg_price: number | null;     // 挂牌均价 (visible_listing_unit_price_avg)
  deal_avg_price: number | null;        // 签约均价 (monthly_deal_avg_latest)
  listing_count: number | null;         // 在售套数
  deal_count: number | null;            // 近30日签约
  snapshot_date: string;
}

// 展示/评分用价格: 优先签约均价, 无则用挂牌均价 (每个小区只有其中一种)
export function getDisplayPrice(price: PriceInfo): number | null {
  return price.deal_avg_price ?? price.listing_avg_price;
}

// 价格区间 -> 颜色 (浅色主题色阶, 地图轮廓/图例/表格共用; 无价灰色)
// 五档为色相递进(绿→黄绿→黄→橙→红), 每档色相差拉满, 避免"深绿/浅绿"式同色系深浅歧义
export function getPriceColor(price: number | null): string {
  if (!price) return '#9AA3AD';
  if (price < 20000) return '#3D9147';
  if (price < 35000) return '#A8C03C';
  if (price < 50000) return '#E5B32C';
  if (price < 70000) return '#E2711D';
  return '#D64545';
}

export interface POI {
  name: string;
  type: POIType;
  distance: number;       // 距小区距离(米)
  latitude: number;
  longitude: number;
}

export type POIType = 'subway' | 'school' | 'hospital' | 'mall' | 'park' | 'bus';

// 地图上展示的 POI 点（跨小区去重后）
export interface MapPOI {
  name: string;
  type: POIType;
  latitude: number;
  longitude: number;
  level?: SchoolLevel;   // 学校类专有: 学段
}

// 学校学段(按名称推断)
export type SchoolLevel = 'kindergarten' | 'primary' | 'middle' | 'university';

export const SCHOOL_LEVEL_LABELS: Record<SchoolLevel, string> = {
  kindergarten: '幼儿园',
  primary: '小学',
  middle: '中学',
  university: '大学',
};

// 紫色系深浅区分学段
export const SCHOOL_LEVEL_COLORS: Record<SchoolLevel, string> = {
  kindergarten: '#C9A7FF',
  primary: '#9B87F5',
  middle: '#7B68EE',
  university: '#5A4BD1',
};

/**
 * 从学校名称推断学段。
 * 返回 null 表示培训机构/文化设施等非学历教育噪音, 不在地图绘制。
 * 九年一贯制/职业学校/专修学校归入中学段。
 */
export function getSchoolLevel(name: string): SchoolLevel | null {
  if (/幼儿园|幼托|托育|学前教育|分园|幼幼|托崽/.test(name)) return 'kindergarten';
  if (/小学/.test(name)) return 'primary';
  if (/大学|学院|研究院|校区|院校/.test(name)) return 'university';
  if (/中学|初中|高中|初级|高级|实验|九年|一贯|职业|专修|中专|技校|学校|school/i.test(name)) return 'middle';
  return null;
}

export interface ScoreResult {
  total_score: number;      // 0-100 综合评分 (缺失维度按剩余权重归一化)
  location_score: number | null;  // 区位价值 (轨交可达性)
  product_score: number | null;   // 产品力 (楼龄)
  amenity_score: number | null;   // 配套 (教育/医疗/商业/公园; 地铁归区位)
  market_score: number | null;    // 市场面 (成交活跃度)
}

// 评分权重配置 (价格不参与评分: 价格是筛选条件而非居住质量, 且已隐含在市场定价中)
// 四维对齐专业评估框架: 区位价值/配套/产品力/市场面, 彼此正交
export interface ScoreWeights {
  location: number; // 区位价值, 默认 30
  amenity: number;  // 配套, 默认 30
  product: number;  // 产品力, 默认 25
  market: number;   // 市场面, 默认 15
}

// POI 分类配置
export interface POIConfig {
  radius: number;     // 搜索半径（米）
  weight: number;      // 权重占比
}

export const POI_CONFIGS: Record<POIType, POIConfig> = {
  subway: { radius: 800, weight: 0.25 },
  school: { radius: 1500, weight: 0.30 },
  hospital: { radius: 2000, weight: 0.15 },
  mall: { radius: 1500, weight: 0.15 },
  park: { radius: 1500, weight: 0.10 },
  bus: { radius: 500, weight: 0.05 },
};

// 预设小区数据（来自 data/binjiang_communities.json + price_snapshots.jsonl）
export const MOCK_COMMUNITIES: Community[] = [
  {
    community_id: '20044031',
    community_name: '万科璞悦湾',
    district: '滨江区',
    subdistrict: '浦沿',
    address: '滨文路与浦沿路交叉口',
    latitude: 30.1749,
    longitude: 120.1785,
    price: {
      listing_avg_price: 40659,
      deal_avg_price: 38500,
      listing_count: 23,
      deal_count: 5,
      snapshot_date: '2026-05-08',
    },
    pois: [
      { name: '浦沿站', type: 'subway', distance: 350, latitude: 30.1755, longitude: 120.1790 },
      { name: '江南实验小学', type: 'school', distance: 800, latitude: 30.1730, longitude: 120.1770 },
      { name: '龙湖天街', type: 'mall', distance: 1200, latitude: 30.1700, longitude: 120.1800 },
    ],
    score: { total_score: 78, location_score: null, amenity_score: 82, product_score: null, market_score: null },
  },
  {
    community_id: '10001734',
    community_name: '世茂之西湖',
    district: '滨江区',
    subdistrict: '浦沿',
    address: '浦沿街道世茂之西湖小区',
    latitude: 30.1812,
    longitude: 120.1856,
    price: {
      listing_avg_price: 47880,
      deal_avg_price: 45200,
      listing_count: 18,
      deal_count: 3,
      snapshot_date: '2026-05-08',
    },
    pois: [
      { name: '中医药大学站', type: 'subway', distance: 500, latitude: 30.1820, longitude: 120.1860 },
      { name: '滨江实验中学', type: 'school', distance: 1000, latitude: 30.1790, longitude: 120.1840 },
      { name: '星光大道', type: 'mall', distance: 800, latitude: 30.1800, longitude: 120.1830 },
    ],
    score: { total_score: 82, location_score: null, amenity_score: 85, product_score: null, market_score: null },
  },
  {
    community_id: '10001735',
    community_name: '世茂之西湖茂御居',
    district: '滨江区',
    subdistrict: '浦沿',
    address: '浦沿街道茂御居',
    latitude: 30.1820,
    longitude: 120.1862,
    price: {
      listing_avg_price: 13290,
      deal_avg_price: 12800,
      listing_count: 45,
      deal_count: 12,
      snapshot_date: '2026-05-08',
    },
    pois: [
      { name: '中医药大学站', type: 'subway', distance: 450, latitude: 30.1825, longitude: 120.1865 },
      { name: '浦沿中心幼儿园', type: 'school', distance: 600, latitude: 30.1830, longitude: 120.1850 },
      { name: '江南时代', type: 'mall', distance: 900, latitude: 30.1810, longitude: 120.1870 },
    ],
    score: { total_score: 65, location_score: null, amenity_score: 70, product_score: null, market_score: null },
  },
];

// 统计数据
export interface DashboardStats {
  total_communities: number;
  avg_price: number;
  max_price: number;
  min_price: number;
}

export interface MarketReferenceRow {
  name: string;
  avg_price: number;
  mom_percent: number;
  map_subdistrict: string;
  map_scope_note: string;
}

export interface MarketReferenceAvailable {
  available: true;
  source: { name: string; url: string; captured_at: string };
  scope: string;
  price_kind: 'listing_reference';
  overall: { avg_price: number; mom_percent: number; yoy_percent: number };
  subdistricts: MarketReferenceRow[];
}

export interface MarketReferenceUnavailable {
  available: false;
  reason: string;
}

export type MarketReference = MarketReferenceAvailable | MarketReferenceUnavailable;

export function isListingReference(value: unknown): value is MarketReferenceAvailable {
  if (!value || typeof value !== 'object') return false;
  const reference = value as Partial<MarketReferenceAvailable>;
  return reference.available === true && reference.price_kind === 'listing_reference'
    && Boolean(reference.source?.name && reference.source.url && reference.source.captured_at)
    && Boolean(reference.overall) && Array.isArray(reference.subdistricts);
}
