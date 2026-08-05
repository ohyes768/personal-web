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
  roe?: number | null;                            // 加权净资产收益率(%)

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
 * 单个红利指数持仓刷新状态（徽章数据源）
 *
 * 新增字段（FR-4：区分"持仓+prefilter 都成功" vs "持仓成功但 prefilter 重算失败"）：
 * - prefilter_resynced: true 表示后端单指数刷成功后本地重算 prefilter 也成功
 * - prefilter_error: 重算失败原因；prefilter_resynced=false 时有意义
 *
 * 后端兼容：旧响应无这两个字段时按 ?? 默认值处理，让前端在部署期间不退化
 * - prefilter_resynced 默认 true（兼容旧后端：仅 success 一项决定）
 * - prefilter_error 默认 null
 */
export interface IndexRefreshItem {
  code: string;
  name: string;
  success: boolean;
  constituents_count: number;
  error?: string | null;
  /** 单指数刷新后是否完成 prefilter 本地重算。徽章显示 ✅ 需要 success + prefilter_resynced 都为 true。 */
  prefilter_resynced?: boolean;
  /** prefilter 重算失败原因（仅 prefilter_resynced=false 时有意义） */
  prefilter_error?: string | null;
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
  /** 各红利指数持仓刷新状态（仅 /dividend/refresh 返回） */
  index_results?: IndexRefreshItem[];
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
export interface HoldingsStatus {
  expected_index_count: number;
  actual_index_count: number;
  expected_index_codes: string[];
  actual_index_codes: string[];
  missing_index_codes: string[];
  holdings_complete: boolean;
}

export interface DividendStatusResponse {
  needs_update: boolean;
  last_updated: string | null;
  file_exists: boolean;
  pending_count: number;
  target_count: number;
  completed_count: number;
  failed_codes: string[];
  /** 持仓 CSV 覆盖度（指数数量是否齐全），后端 /dividend/status 返回 */
  holdings_status?: HoldingsStatus;
}

/**
 * 股息率统计信息（来自 GET /api/dividend/stats）
 * 字段含义见 backend/dividend-select/src/api/routes.py::get_stats
 */
export interface StatsResponse {
  /** 全量股票数（未应用 min_yield 筛选） */
  total_stocks: number;
  yield_stats: {
    max: number | null;
    min: number | null;
    median: number | null;
    mean: number | null;
  };
  /** 3年股息率分桶计数 */
  yield_distribution: {
    above_6: number;
    above_5: number;
    above_4: number;
    above_3: number;
  };
  industry_distribution: Record<string, number>;
  index_distribution: Record<string, number>;
  csv_last_modified: string | null;
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
  nonRecurringYoYIndex: number | null; // 扣非净利润同比，最大值为最优
  cagr3yIndex: number | null;          // 3年复合增长率，最大值为最优
  roeIndex: number | null;             // 加权净资产收益率，最大值为最优
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

// ========== 挡位监控（alerts）类型 ==========

/**
 * 单档挡位（价格必填，PE 选填仅作推送展示）
 */
export interface AlertLevel {
  price: number;
  pe?: number | null;
}

/**
 * 4 档挡位配置
 * - heavy_position  🟢 重仓（买入最深）
 * - add_position    🟡 加仓
 * - reduce_position 🟠 减仓
 * - full_exit       🔴 全卖（卖出最深）
 */
export interface AlertLevels {
  heavy_position?: AlertLevel | null;
  add_position?: AlertLevel | null;
  reduce_position?: AlertLevel | null;
  full_exit?: AlertLevel | null;
}

/**
 * 单只股票的挡位监控配置
 */
export interface AlertConfig {
  enabled: boolean;
  /** 最后更新时间 (ISO 8601)，由后端自动记录，前端只读 */
  updated_at?: string | null;
  levels: AlertLevels;
}

/**
 * 挡位配置更新请求（前端 → 后端）
 *
 * 不带 updated_at：后端在写入时自动 ts 戳，前端不可伪造。
 */
export type AlertConfigRequest = Pick<AlertConfig, 'enabled' | 'levels'>;

/**
 * 挡位状态条目（GET /favorites/alerts/status 返回）
 */
export interface AlertStatusItem {
  code: string;
  name?: string | null;
  enabled: boolean;
  has_levels: boolean;
  level_count: number;
  /** 挡位最后更新时间（ISO 8601），未配置过返回 null */
  updated_at?: string | null;
  levels?: AlertLevels | null;
  triggered_today: string[];  // 今日此股触发的 level_key 列表
}

/**
 * 挡位状态响应
 */
export interface AlertStatusResponse {
  total: number;
  enabled_count: number;
  triggered_today_count: number;
  dingtalk_configured: boolean;
  items: AlertStatusItem[];
}

/**
 * 手动触发挡位检查的返回
 */
export interface AlertCheckResult {
  checked_at: string;
  scanned: number;
  triggered: Array<{
    code: string;
    name: string;
    level_key: string;
    level_label: string;
    level_emoji: string;
    direction: 'buy' | 'sell';
    level_price: number;
    level_pe?: number | null;
    current_price: number;
    current_pe?: number | null;
    distance_pct: number;
    strategy?: string | null;
    star_rating?: number | null;
    doc_url?: string | null;
    triggered_at: string;
  }>;
  pushed: boolean;
  push_error?: string | null;
}

/**
 * 挡位 key 标签映射（前端展示用）
 */
export const LEVEL_META = {
  heavy_position:  { label: '重仓档', emoji: '🟢', direction: 'buy'  as const, severity: 2 },
  add_position:    { label: '加仓档', emoji: '🟡', direction: 'buy'  as const, severity: 1 },
  reduce_position: { label: '减仓档', emoji: '🟠', direction: 'sell' as const, severity: 1 },
  full_exit:       { label: '全卖档', emoji: '🔴', direction: 'sell' as const, severity: 2 },
};

export type LevelKey = keyof typeof LEVEL_META;

// ========== 定时任务（scheduler）类型 ==========

/**
 * 单次执行结果（GET /api/dividend/scheduler/jobs/{job_id}/runs 返回）
 */
export interface SchedulerJobRun {
  start: string;
  end?: string | null;
  status: 'success' | 'skipped' | 'failed';
  count?: number | null;
  reason?: string | null;
  error?: string | null;
}

/**
 * 调度任务（GET /api/dividend/scheduler/jobs 返回）
 */
export interface SchedulerJob {
  id: string;
  name: string;
  target: string;
  cron: string;
  cron_human: string;
  enabled: boolean;
  next_run_time?: string | null;
  last_run?: SchedulerJobRun | null;
  description?: string;
}

/**
 * 立即触发响应（POST /scheduler/jobs/{id}/run 返回）
 */
export interface SchedulerTriggerResponse {
  job_id: string;
  triggered_at: string;
}
