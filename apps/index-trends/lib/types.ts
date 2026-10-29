/** 后端 API 类型镜像（与 backend/index-trends 响应结构一一对应）。 */

export type ModelKind = "trailing_120m" | "since_inception" | "historical_fixed_120m";

export interface Coefficients {
  slope: number;
  intercept: number;
  deviation: number;
}

export interface ModelInfo {
  model_id: string;
  index_code: string;
  kind: ModelKind;
  fit_start: string;
  fit_end: string;
  months: number;
  algorithm_version: string;
  data_cutoff_month: string;
  multiplier: number;
  calculated_at: string;
  coefficients: Coefficients;
}

export interface DataStatus {
  state: "ok" | "stale" | "empty";
  data_cutoff_month: string | null;
  expected_cutoff_month: string;
  daily_last_date: string | null;
  captured_at: string | null;
  provider: string | null;
}

export interface WindowMeta {
  stable_id: string;
  window: number;
  fit_start: string;
  fit_end: string;
  observation_end_month: string | null;
  model_id: string;
}

export interface AllHistoryMeta {
  stable_id: "all";
  fit_start: string;
  fit_end: string;
  sample_fitted: boolean;
  model_id: string;
  note: string;
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
    inception_month: string;
    available_model_kinds: ModelKind[];
    current_models: Partial<Record<"trailing_120m" | "since_inception", ModelInfo>>;
  }>;
  data_status: DataStatus;
}

export interface ChartBar {
  month: string;
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  partial: boolean;
}

export interface ChannelSeries {
  months: string[];
  mid: number[];
  upper: number[];
  lower: number[];
}

export interface ChartData {
  model: ModelInfo;
  bars: ChartBar[];
  fit_series: ChannelSeries;
  extension_series: ChannelSeries | null;
  fit_boundary_month: string;
  extend_note: string | null;
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
  price_as_of?: string;
  close?: number;
  projection_month?: string;
  upper?: number;
  mid?: number;
  lower?: number;
  position_pct?: number;
  region?: Region;
  data_status?: DataStatus;
  error?: string;
}

export interface ReportSettings {
  index_code: string;
  model_kind: ModelKind;
  enabled: boolean;
  send_cron: string;
  channel: string;
  updated_at: string;
}

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
  trailing_120m: "近10年",
  since_inception: "成立以来",
  historical_fixed_120m: "固定窗口",
};
