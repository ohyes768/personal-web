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

  // 2022 年数据
  avg_price_2022?: number | null;
  dividend_2022?: number | null;
  dividend_count_2022?: number | null;
  yield_2022?: number | null;

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

  // 股东户数（散户数）
  shareholder_count?: number | null;      // 股东户数
  shareholder_change_pct?: number | null; // 股东人数增幅(%)
  per_share_holding?: number | null;      // 人均持股数量

  // 财务指标 - 成长能力
  net_profit_ex_non_recurring_yoy?: number | null; // 扣非净利润同比(%)
  net_profit_cagr_3y?: number | null;             // 3年复合增长率(%)
  eps?: number | null;                            // 最近一期年报基本每股收益(元)
  eps_year?: number | null;                       // 最近一期年报年度
  payout_ratio?: number | null;                   // 分红比例(%)：DPS/EPS×100

  // 财务指标 - 最新季度（2026Q1 vs 2025Q1）
  latest_quarter_net_profit_ex_non_recurring?: number | null; // 最新季度扣非净利润(元)
  latest_quarter_yoy_pct?: number | null;                      // 最新季度扣非同比(%)

  // 近5年分红详情
  dividend_history?: DividendHistoryItem[] | null;
}

/**
 * 单次分红记录
 */
export interface DividendHistoryItem {
  ex_date: string;       // 除权除息日 (YYYY-MM-DD)
  ratio: number;         // 派息比例 (元/股)
  fiscal_year: number;  // 财年
}

// ========== 响应类型 ==========

/**
 * 股票列表响应
 */
export interface DividendListResponse {
  total: number;
  items: DividendStock[];
  last_updated?: string | null;
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
 * M120 股票数据
 */
export interface M120Stock {
  code: string;
  name: string;
  avg_yield_3y?: number | null;
  m120?: number | null;
  close?: number | null;
  deviation?: number | null;
  realtime?: number | null;
  realtime_deviation?: number | null;
  yield_ttm?: number | null;  // 实时股息率TTM(%)
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
  m120?: number | null;
  close?: number | null;           // 昨日收盘价（从实时价格CSV获取）
  deviation?: number | null;       // 昨日收盘与M120的偏离度
  realtime?: number | null;       // 实时价格（从实时价格CSV获取）
  realtimeDeviation?: number | null; // 实时价格与M120的偏离度
  yield_ttm?: number | null;      // 实时股息率TTM(%)
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

/**
 * 股息率刷新统计
 */
export interface RefreshStats {
  total_processed: number;
  new_or_updated: number;
  skipped: number;
  target_count: number;
  completed_count: number;
  failed_count: number;
  failed_codes: string[];
  file_path: string;
  start_time: string;
  end_time: string;
}

/**
 * 股息率刷新响应
 */
export interface RefreshDividendResponse {
  success: boolean;
  message: string;
  stats: RefreshStats;
}

/**
 * 股息率数据状态响应
 */
export interface DividendStatusResponse {
  needs_update: boolean;
  last_updated: string | null;
  file_exists: boolean;
  pending_count: number;
  target_count: number;
  completed_count: number;
  failed_codes: string[];
}

/**
 * 辅助数据状态（行业/财务/户数）
 */
export interface AuxDataStatus {
  exists: boolean;
  last_updated: string | null;
  days_since_update: number | null;
  quarter: string | null;
  needs_update: boolean;
  missing_count?: number;
  missing_codes?: string[];
  record_count?: number;
}

// ========== 板块信息类型 ==========

/**
 * 股票板块信息（概念板块/行业板块）
 */
export interface BoardInfo {
  code: string;
  name: string;
  concept_board?: string | null;
  industry_board?: string | null;
}

/**
 * 板块信息请求参数
 */
export interface BoardInfoRequest {
  code?: string;
  codes?: string;
}

/**
 * 板块信息响应
 */
export interface BoardInfoResponse {
  total: number;
  items: BoardInfo[];
  last_updated?: string | null;
}

// ========== 股票对比功能类型 ==========

/**
 * 高亮信息
 */
export interface HighlightInfo {
  yieldIndex: number | null;
  peIndex: number | null;
  pbIndex: number | null;
  ratioIndex: number | null;  // 昨日收盘/M120 比率，最小值为最优
  highChangeIndex: number | null;  // 最高涨幅，最大值为最优
  lowChangeIndex: number | null;   // 最高跌幅，绝对值最小为最优
}

/**
 * 对比浮动栏 Props
 */
export interface CompareFloatingBarProps {
  selectedCount: number;
  selectedStocks: DividendStock[];
  maxSelect: number;
  onOpenCompare: () => void;
  onClear: () => void;
  isVisible: boolean;
}

/**
 * 对比抽屉 Props
 */
export interface CompareDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  stocks: DividendStockWithTechnical[];
  onRemove: (code: string) => void;
  drawerRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * 对比表格 Props
 */
export interface CompareTableProps {
  stocks: DividendStockWithTechnical[];
  onRemove: (code: string) => void;
}
