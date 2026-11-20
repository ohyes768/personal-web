/** 后端 API 类型镜像（与 backend/index-trends 响应结构一一对应）。
 *
 * 口径：周线。模型拟合使用「完整交易周」，状态可用最新日收盘投影——
 * 周主键是周一（YYYY-MM-DD），行情的 date 是该周实际最后交易日。
 * 不把周值写进 month 命名字段。
 */

/** 当前页可选的两个模型种类（周线）。 */
export type CurrentModelKind = "trailing_10y_weekly" | "since_inception_weekly";

/** 全部模型种类（周线）。历史固定窗口用 stable_id 做页面稳定选项。 */
export type ModelKind =
  | CurrentModelKind
  | "historical_fixed_10y_weekly";

/** 当前后端只提供周线模型。 */
export type Timeframe = "week";

export interface Coefficients {
  slope: number;
  intercept: number;
  deviation: number;
}

export interface ModelInfo {
  model_id: string;
  index_code: string;
  kind: ModelKind;
  timeframe: Timeframe;
  /** 首个样本周的周一。 */
  fit_start: string;
  /** 末个样本周的周一。 */
  fit_end: string;
  /** 末个样本周的实际最后交易日。 */
  fit_last_trade_date: string;
  /** 实际参与拟合的交易周数量。 */
  sample_count: number;
  /** 日历窗口左边界（含）。 */
  calendar_window_start: string;
  /** 日历窗口右边界（不含）。 */
  calendar_window_end: string;
  /** 已发布的截止周（周一）。 */
  data_cutoff_week: string;
  algorithm_version: string;
  multiplier: number;
  calculated_at: string;
  coefficients: Coefficients;
}

export interface RefreshResult {
  success: boolean;
  message: string;
  data_cutoff_week: string | null;
  new_models: string[] | null;
  weekly_count: number | null;
  snapshot_id: string | null;
}

export type DataState = "ok" | "stale" | "empty" | "error";
export interface DataStatus {
  state: DataState;
  data_cutoff_week: string | null;
  expected_cutoff_week: string | null;
  /** 最近应完成的自然周的周一。 */
  expected_close_date: string | null;
  daily_last_date: string | null;
  captured_at: string | null;
  reason: string | null;
  snapshot_id: string | null;
  /** 行情来源（可选，后端未提供时不显示）。 */
  provider?: string | null;
}

export interface WindowMeta {
  /** 页面稳定选项，如 fixed-2024-04。 */
  stable_id: string;
  /** 窗口序号（可选，缺省时按列表顺序）。 */
  window?: number;
  calendar_window_start: string;
  calendar_window_end: string;
  /** 首个样本周的周一。 */
  fit_start: string;
  /** 末个样本周的周一。 */
  fit_end: string;
  observation_end_week: string | null;
  sample_count: number;
  model_id: string;
}

export interface AllHistoryMeta {
  stable_id: "all";
  calendar_window_start: string;
  calendar_window_end: string;
  fit_start: string;
  fit_end: string;
  observation_end_week: string | null;
  sample_count: number;
  model_id: string;
  note?: string;
}

export interface HistoryOverview {
  index_code: string;
  name: string;
  windows: WindowMeta[];
  all_history: AllHistoryMeta | null;
  data_status: DataStatus;
}

export interface IndicesOverview {
  indices: Array<{
    index_code: string;
    name: string;
    symbol: string;
    kind: string;
    inception_week: string;
    available_model_kinds: ModelKind[];
    current_models: Partial<Record<CurrentModelKind, ModelInfo>>;
    /** 该指数是否有回归通道。 */
    has_channel?: boolean;
    /** 该指数自己的数据新鲜度（多指数后每个指数各一份）。 */
    data_status?: DataStatus;
  }>;
  data_status: DataStatus;
}

/** 一根周 K 线：week_start 是周一，date 是该周实际最后交易日。 */
export interface ChartBar {
  week_start: string;
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  /** 该周尚未走完（进行中），不参与拟合。 */
  partial: boolean;
}

/** 通道序列：weeks 覆盖所有自然周（周一），含整周休市的时间槽。 */
export interface ChannelSeries {
  weeks: string[];
  mid: number[];
  upper: number[];
  lower: number[];
}

export interface ChartData {
  model: ModelInfo;
  bars: ChartBar[];
  fit_series: ChannelSeries;
  extension_series: ChannelSeries | null;
  fit_boundary_week: string;
  extend_note: string | null;
  snapshot_id: string;
}

export type Region =
  | "below_channel"
  | "lower"
  | "middle"
  | "upper"
  | "above_channel";

export interface CurrentStatus {
  available: boolean;
  model_kind?: ModelKind;
  reason?: string;
  model?: ModelInfo;
  /** 实际收盘日。 */
  price_as_of?: string;
  close?: number;
  /** 投影所在自然周的周一。 */
  projection_week?: string;
  upper?: number;
  mid?: number;
  lower?: number;
  position_pct?: number;
  region?: Region;
  data_status?: DataStatus;
  error?: string;
  snapshot_id?: string;
  /** 理杏仁估值（可选：旧后端不提供时按不可用展示）。 */
  valuation?: Valuation | null;
  /** 该指数是否有回归通道；无通道时响应里不含 position_pct / upper / lower。 */
  has_channel?: boolean;
}

/** 周价格序列（不依赖通道模型）。 */
export interface PriceBar {
  week_start: string;
  date: string;
  close: number;
  high: number;
  low: number;
  partial: boolean;
}

export interface PriceSeries {
  index_code: string;
  name: string;
  has_channel: boolean;
  bars: PriceBar[];
  close: number | null;
  price_as_of: string | null;
  data_status: DataStatus;
  snapshot_id: string | null;
}

/** 估值状态：与行情状态独立，估值异常不阻断行情与图表。 */
export type ValuationState = "ok" | "stale" | "empty" | "error" | "disabled";

/** 两条估值指标：PB 为主，PE-TTM 为辅（各自独立判状态）。 */
export type ValuationMetric = "pb_mcw" | "pe_ttm_mcw";

export const VALUATION_METRIC_LABELS: Record<ValuationMetric, string> = {
  pb_mcw: "PB 分位",
  pe_ttm_mcw: "PE 分位",
};

/** 单条指标的状态快照。 */
export interface ValuationMetricSnapshot {
  state: ValuationState;
  reason: string | null;
  metric: string;
  source: string;
  window: string;
  target_date: string | null;
  as_of: string | null;
  /** 指标当前数值：PB 时是市净率，PE 时是市盈率。 */
  value: number | null;
  percentile_pct: number | null;
  captured_at: string | null;
}

/** 分位历史序列（分位走势图数据源）。 */
export interface ValuationHistory {
  index_code: string;
  metric: string;
  window: string;
  dates: string[];
  values: number[];
  percentiles: (number | null)[];
}

export interface Valuation {
  state: ValuationState;
  /** 固定错误码（不含供应商正文）。 */
  reason: string | null;
  source: string;
  metric: string;
  /** 分位窗口（如 y10 = 近10年）。 */
  window: string;
  /** 期望的数据日期（最近已收盘交易日）。 */
  target_date: string | null;
  /** 实际数据日期。 */
  as_of: string | null;
  /** 当前指标数值（顶层按 PE-TTM 平铺，兼容既有调用）。 */
  value?: number | null;
  /** PE-TTM（总市值加权）。 */
  pe_ttm: number | null;
  /** 近 N 年分位（0–100）。 */
  percentile_pct: number | null;
  captured_at: string | null;
  /** 全部指标的完整状态；旧后端不提供时只有顶层 PE 字段。 */
  metrics?: Partial<Record<ValuationMetric, ValuationMetricSnapshot>>;
}

/** 退役周报的历史存档；新简报由 Hermes 生成和投递。 */
export interface ReportRecord {
  idempotency_key: string;
  index_code: string;
  iso_week: string;
  model_id: string;
  model_kind: string;
  business_status: string;
  close: number | null;
  close_date: string | null;
  region: string | null;
  position_pct: number | null;
  content: string;
  status: string;
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

export const REGION_LABELS: Record<Region, string> = {
  below_channel: "通道下方",
  lower: "低位",
  middle: "中部",
  upper: "高位",
  above_channel: "通道上方",
};

export const KIND_LABELS: Record<string, string> = {
  trailing_10y_weekly: "近10年",
  since_inception_weekly: "成立以来",
  historical_fixed_10y_weekly: "固定窗口",
};
