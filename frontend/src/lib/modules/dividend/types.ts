/**
 * 股息率模块类型定义
 */

// ========== 实体类型 ==========

/**
 * 单季度数据
 */
export interface Quarter {
  avg_price?: number | null;
  dividend?: number | null;
  yield_pct?: number | null;
}

/**
 * 季度数据
 */
export interface QuarterlyData {
  q1?: Quarter | null;
  q2?: Quarter | null;
  q3?: Quarter | null;
  q4?: Quarter | null;
}

/**
 * 股息率股票数据
 */
export interface DividendStock {
  // 基础信息
  code: string;
  name: string;
  exchange: string;
  source_index?: string | null;
  sw_level1?: string | null;
  sw_level2?: string | null;
  sw_level3?: string | null;
  concept_board?: string | null;
  industry_board?: string | null;

  // 2025 年数据
  avg_price_2025?: number | null;
  dividend_2025?: number | null;
  dividend_count_2025?: number | null;
  yield_2025?: number | null;

  // 2024 年数据
  avg_price_2024?: number | null;
  dividend_2024?: number | null;
  dividend_count_2024?: number | null;
  yield_2024?: number | null;

  // 2023 年数据
  avg_price_2023?: number | null;
  dividend_2023?: number | null;
  dividend_count_2023?: number | null;
  yield_2023?: number | null;

  // 3 年平均
  avg_price_3y?: number | null;
  avg_yield_3y?: number | null;

  // 2025 年价格波动
  high_price_2025?: number | null;
  low_price_2025?: number | null;
  high_change_pct_2025?: number | null;
  low_change_pct_2025?: number | null;

  // 季度数据
  quarterly?: QuarterlyData | null;
}

// ========== 响应类型 ==========

/**
 * 股票列表响应
 */
export interface DividendListResponse {
  total: number;
  items: DividendStock[];
}

/**
 * 股票详情响应
 */
export interface DividendDetailResponse {
  data: DividendStock;
  quarterly: QuarterlyData;
}

// ========== 查询参数类型 ==========

/**
 * 股票列表查询参数
 */
export interface DividendQueryParams {
  min_yield?: number | null;
  max_yield?: number | null;
  exchange?: string | null;
  industry?: string | null;
  index?: string | null;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

// ========== 组件 Props 类型 ==========

/**
 * 详情弹框类型
 */
export type DetailModalType = 'quarterly' | 'sector' | 'yearly' | 'volatility';

/**
 * 详情弹框 Props
 */
export interface DetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: DetailModalType | null;
  stock: DividendStock | null;
}

// ========== 技术指标类型 ==========

/**
 * 股票 PE 数据
 */
export interface StockPE {
  code: string;
  name: string;
  pe?: number | null;
  pb?: number | null;
  market_cap?: number | null;        // 总市值（万元）
  circulation_market_cap?: number | null;  // 流通市值（万元）
}

/**
 * PE 数据响应
 */
export interface StockPEResponse {
  total: number;
  items: StockPE[];
  last_updated?: string | null;
}

/**
 * M120 股票数据
 */
export interface M120Stock {
  code: string;
  name: string;
  avg_yield_3y?: number | null;
  m120?: number | null;
  close?: number | null;
  deviation?: number | null;
}

/**
 * M120 列表响应
 */
export interface M120ListResponse {
  total: number;
  items: M120Stock[];
  last_updated?: string | null;
}

/**
 * 实时股价请求
 */
export interface RealtimePriceRequest {
  code: string;
  m120: number;
}

/**
 * 实时股价响应
 */
export interface RealtimePriceResponse {
  code: string;
  close?: number | null;
  deviation?: number | null;
  timestamp?: string | null;
}

/**
 * 技术指标数据
 */
export interface TechnicalIndicators {
  pe?: number | null;
  pb?: number | null;
  m120?: number | null;
  close?: number | null;           // 昨日收盘价（从 M120 数据获取）
  deviation?: number | null;       // 与 M120 的偏离度（从 M120 数据获取）
  realtimeClose?: number | null;   // 实时价格（刷新后更新）
  realtimeDeviation?: number | null; // 实时偏离度（刷新后更新）
}

/**
 * 带技术指标的股票数据
 */
export interface DividendStockWithTechnical extends DividendStock {
  technical?: TechnicalIndicators;
}

/**
 * 偏离度缓存数据
 */
export interface DeviationCache {
  close: number;
  deviation: number;
  timestamp: number;
}

/**
 * 刷新状态
 */
export interface RefreshState {
  loading: boolean;
  error: string | null;
}

// ========== 股票信息类型 ==========

/**
 * 股票行业/概念信息
 */
export interface StockInfo {
  code: string;
  exchange?: string | null;
  sw_level1?: string | null;
  sw_level2?: string | null;
  sw_level3?: string | null;
  concept_board?: string | null;
  industry_board?: string | null;
}

/**
 * 股票信息请求
 */
export interface StockInfoRequest {
  codes: string[];
}

/**
 * 股票信息响应
 */
export interface StockInfoResponse {
  items: StockInfo[];
  total: number;
}