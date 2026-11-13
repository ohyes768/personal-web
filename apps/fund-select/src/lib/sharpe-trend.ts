/**
 * 夏普走势（GET /api/funds/sharpe-trend/{code}）独立 DTO / URL 参数 / 请求
 *
 * - DTO 与后端 src/api/models.py 的 3 个 SharpeTrend* DTO 逐字段对齐
 *   （contracts §3a：后端加字段要三处同步：models.py ↔ 本文件 ↔ 页面）
 * - fetch 必须写全路径 `/funds/api/funds/...`（原生 fetch 不吃 basePath）
 * - URL 参数与后端 Query 校验对齐；非法值解析时回退默认（不抛错）
 * - 页面是纯只读现算，任何筛选都不触发采集
 */
'use client';

export type SharpeTrendRange = 'all' | '3y' | '1y';

/** 一个周观测点：该自然周最后一个交易日的 trailing-3y 夏普 */
export interface SharpeTrendPoint {
  /** YYYY-MM-DD */
  date: string;
  /** null = 样本不足 / 无定义（前端断线不补零） */
  sharpe: number | null;
  sample_days: number;
}

/** 展示区间内稳定性统计（null 表示无定义 / 点数不足） */
export interface SharpeTrendStats {
  threshold: number;
  current: number | null;
  max: number | null;
  min: number | null;
  mean: number | null;
  above_count: number;
  valid_count: number;
  /** 0..1；null 表示无有效点 */
  above_ratio: number | null;
  /** 从最新点往回，连续 ≥ threshold 的周数 */
  consecutive_above: number;
  /** 全区最长连续 < threshold 的周数 */
  longest_below: number;
  /** 最近 12 个有效点的线性斜率（每周变化量）；不足 12 点 → null */
  trend_12w: number | null;
}

export interface SharpeTrendResponse {
  code: string;
  name: string | null;
  range: SharpeTrendRange;
  /** zero = risk_free_rate 表为空按 rf=0（生产库现状）；rate = 用库内利率 */
  rf_basis: 'zero' | 'rate';
  algorithm_version: string;
  threshold: number;
  points: SharpeTrendPoint[];
  stats: SharpeTrendStats;
  diagnostics: {
    insufficient_history?: boolean;
    no_valid_points?: boolean;
    nav_end_date?: string | null;
    total_points?: number;
    total_return_days?: number;
    [key: string]: unknown;
  };
}

export const TREND_RANGES: SharpeTrendRange[] = ['all', '3y', '1y'];

export const TREND_RANGE_OPTIONS: { value: SharpeTrendRange; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: '3y', label: '近 3 年' },
  { value: '1y', label: '近 1 年' },
];

export const DEFAULT_TREND_RANGE: SharpeTrendRange = 'all';
/** 与夏普榜单入选线一致（design R2 / 用户决策） */
export const DEFAULT_TREND_THRESHOLD = 0.8;
/** 6 位基金代码 */
export const FUND_CODE_PATTERN = /^\d{6}$/;

/** 从 URL 解析走势页参数；非法值逐字段回退默认（不抛错） */
export function parseSharpeTrendSearch(search: URLSearchParams): {
  code: string | null;
  range: SharpeTrendRange;
} {
  const codeRaw = search.get('code');
  const code = codeRaw && FUND_CODE_PATTERN.test(codeRaw) ? codeRaw : null;
  const rangeRaw = search.get('range');
  const range = rangeRaw && (TREND_RANGES as string[]).includes(rangeRaw)
    ? (rangeRaw as SharpeTrendRange)
    : DEFAULT_TREND_RANGE;
  return { code, range };
}

/** 生成走势页 URL（相对 basePath，不带 /funds 前缀 —— §4 双前缀陷阱） */
export function sharpeTrendHref(code: string, range: SharpeTrendRange = 'all'): string {
  const qs = new URLSearchParams({ code });
  if (range !== DEFAULT_TREND_RANGE) qs.set('range', range);
  const q = qs.toString();
  return `/sharpe-trend${q ? `?${q}` : ''}`;
}

/** 区间切换时保留 code，只改 range（默认值不写 URL） */
export function trendRangeHref(code: string, range: SharpeTrendRange): string {
  return sharpeTrendHref(code, range);
}

/**
 * 请求走势数据。AbortController 信号用于 code/range 切换时中止旧请求，
 * 防止旧响应覆盖新状态（与 sharpe-board source 切换同一坑）。
 */
export async function fetchSharpeTrend(
  code: string,
  range: SharpeTrendRange = DEFAULT_TREND_RANGE,
  signal?: AbortSignal,
): Promise<SharpeTrendResponse> {
  const qs = new URLSearchParams();
  if (range !== DEFAULT_TREND_RANGE) qs.set('range', range);
  const q = qs.toString();
  const res = await fetch(
    `/funds/api/funds/sharpe-trend/${encodeURIComponent(code)}${q ? `?${q}` : ''}`,
    { cache: 'no-store', signal },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`请求失败 ${res.status}: ${detail.slice(0, 160)}`);
  }
  return res.json() as Promise<SharpeTrendResponse>;
}

// ─────────────────────────────────────────────────────────────
// 展示格式化 / 状态分类（纯函数，node:test 直跑）
// ─────────────────────────────────────────────────────────────

export type SharpeTrendPhase =
  | 'needs-code'
  | 'insufficient'
  | 'no-valid'
  | 'ok';

/** 主状态分类（error 由请求层抛出，单独呈现可重试） */
export function classifySharpeTrend(data: SharpeTrendResponse | null): SharpeTrendPhase {
  if (data === null) return 'needs-code';
  if (data.diagnostics.insufficient_history) return 'insufficient';
  if (data.points.length === 0 || data.stats.valid_count === 0) return 'no-valid';
  return 'ok';
}

/** 夏普数值展示（2 位小数；null → '—'） */
export function formatSharpe(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(2);
}

/** 百分比（0..1 → '78%'；null → '—'） */
export function formatRatio(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v)
    ? '—'
    : `${Math.round(v * 100)}%`;
}

/** 近 12 周斜率：带符号、4 位小数、附单位（每周变化） */
export function formatSlope(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(4)}/周`;
}

/** 日期 YYYY-MM-DD → MM-DD（图轴标签用） */
export function formatShortDate(iso: string): string {
  return iso.length >= 10 ? iso.slice(5, 10) : iso;
}

/** 达标状态配色语义（供 KPI 卡复用） */
export function sharpeLevel(v: number | null, threshold: number): 'good' | 'bad' | 'na' {
  if (v === null || !Number.isFinite(v)) return 'na';
  return v >= threshold ? 'good' : 'bad';
}
