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