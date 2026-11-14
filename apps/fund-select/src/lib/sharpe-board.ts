/**
 * 夏普榜单（GET /api/funds/sharpe-board）独立 DTO / URL 参数 / 请求
 *
 * - DTO 与后端 src/api/models.py 六个 SharpeBoard* DTO 对齐（只读契约）
 * - fetch 必须写全路径 /funds/api/funds/...（原生 fetch 不吃 basePath）
 * - URL 参数与后端 Query 校验对齐；非法值解析时回退默认（不抛错）
 * - 展示筛选只影响呈现，记录规则在后端 profile 里，前端只读展示（R5）
 */
'use client';

/** 榜单来源：all = 两条链路聚合（11-15-source-segmented），stock = 三分法，discovery-stock = 市场 */
export type SharpeSource = 'all' | 'stock' | 'discovery-stock';
/** 图时间范围：all = 近一年(52 周)。旧 '1y' 与 all 等价，已从下拉移除 */
export type SharpeRange = '3m' | '6m' | 'all';

/** 固定规则 profile（source/version/filters/prefilters/algorithm） */
export interface SharpeBoardProfile {
  source: string;
  version: string;
  filters: Record<string, number | boolean>;
  collection_prefilters: Record<string, number>;
  market_subtypes: string[] | null;
  algorithm_version: string;
}

/** 最新一次周榜尝试（任意状态；失败时 errors 原文透出） */
export interface SharpeBoardAttempt {
  week_start: string;
  status: string;
  trigger: string | null;
  started_at: string | null;
  finished_at: string | null;
  selected_count: number;
  errors: string[];
}

/** 榜单列表项（后端排序：listed_weeks DESC, latest_sharpe DESC, code ASC） */
export interface SharpeBoardItem {
  code: string;
  name: string;
  /** v2：52 周窗口内在榜周数（不是全历史累计） */
  listed_weeks: number;
  /** 可评周数（分母）：窗口内该基金有有效样本的周数（数据缺口周不计入） */
  evaluable_weeks: number;
  consecutive_weeks: number;
  /** 该基金在榜期间的数据缺口周（无榜 / 样本未更新）；不计入在榜、不打断连续 */
  gap_weeks: string[];
  /** 最近上榜夏普（不是「当前夏普」，R3） */
  latest_sharpe: number | null;
  last_listed_week: string | null;
  on_latest_board: boolean;
  /** 近 1 年/近 3 年收益（实时表当前值，仅展示） */
  ret_1y: number | null;
  ret_3y: number | null;
  /** v2：近 12 周夏普≥0.8 的周数 / 分母（不足12周为实际周数） */
  near_12w_qualified: number | null;
  near_12w_total: number | null;
  /** v2 滚动口径：同类排名分位（%，如前 14.2%）与数据日期 */
  peer_pct: number | null;
  peer_as_of: string | null;
  /** v3 年度口径：各年分位 / 达标年数 / 评估年度窗口 */
  peer_years: Record<string, number | null> | null;
  peer_qualified_years: number | null;
  peer_window: string[] | null;
}

/** 曲线序列（全部命中基金，不随 items 分页；values 长度 == weeks 长度） */
export interface SharpeBoardSeries {
  code: string;
  name: string;
  values: (number | null)[];
}

/** 数据状态透明化（成功空榜/采集失败/样本未更新可区分） */
export interface SharpeBoardDiagnostics {
  no_board_weeks: string[];
  /** 周历内数据不可用的周：没发榜，或该周有基金样本未更新（节假日休市等） */
  gap_weeks: string[];
  latest_diagnostics: Record<string, unknown>;
}

export interface SharpeBoardResponse {
  profile: SharpeBoardProfile;
  /** 最新 complete 周周一（失败/停机时是旧榜日期） */
  latest_published_week: string | null;
  latest_attempt: SharpeBoardAttempt | null;
  /** 当前自然周无 complete 榜 → true，不冒充本周 */
  stale: boolean;
  total: number;
  items: SharpeBoardItem[];
  /** 统一周历（周一日期），range 只裁起点 */
  weeks: string[];
  series: SharpeBoardSeries[];
  diagnostics: SharpeBoardDiagnostics;
}

// ─────────────────────────────────────────────────────────────
// URL 参数（design「API 与统计合同」参数面；默认值不写 URL）
// ─────────────────────────────────────────────────────────────

export interface SharpeBoardFilters {
  source: SharpeSource;
  profileVersion: string;
  /** 展示下限：最近上榜夏普 ≥ X（含等于）；null = 不限 */
  minLatestSharpe: number | null;
  /** 在榜占比下限（%，在榜周数 ÷ 可评周数；0=不限） */
  minListedPct: number;
  /** 只看最新成功一周在榜的基金 */
  latestOnly: boolean;
  /** 图时间范围（只裁图，不改统计与命中集合） */
  range: SharpeRange;
  page: number;
  limit: number;
}

export const DEFAULT_SHARPE_FILTERS: SharpeBoardFilters = {
  source: 'all',
  profileVersion: 'v3',
  minLatestSharpe: null,
  minListedPct: 60,
  latestOnly: false,
  range: 'all',
  page: 1,
  limit: 50,
};

export const SOURCE_OPTIONS: { value: SharpeSource; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'discovery-stock', label: '市场' },
  { value: 'stock', label: '三分法' },
];

export const RANGE_OPTIONS: { value: SharpeRange; label: string }[] = [
  // 窗口恒为最近 52 周，range 只是窗口内的缩放；旧 '1y' 与 'all' 等价已移除，
  // 按时长升序排列
  { value: '3m', label: '近 3 个月' },
  { value: '6m', label: '近 6 个月' },
  { value: 'all', label: '近一年(52周)' },
];

const SOURCES = new Set<string>(SOURCE_OPTIONS.map(o => o.value));
const RANGES = new Set<string>(RANGE_OPTIONS.map(o => o.value));

/** 从 URL 解析展示筛选；非法值逐字段回退默认（不抛错） */
export function parseSharpeFiltersFromSearch(search: URLSearchParams): SharpeBoardFilters {
  const sourceRaw = search.get('source');
  const rangeRaw = search.get('range');
  const minSharpeRaw = search.get('min_latest_sharpe');
  const minPctRaw = search.get('min_listed_pct');
  const pageRaw = search.get('page');
  const limitRaw = search.get('limit');
  const filters: SharpeBoardFilters = { ...DEFAULT_SHARPE_FILTERS };
  if (sourceRaw && SOURCES.has(sourceRaw)) filters.source = sourceRaw as SharpeSource;
  const versionRaw = search.get('profile_version');
  if (versionRaw && versionRaw.length >= 1 && versionRaw.length <= 16) filters.profileVersion = versionRaw;
  if (minSharpeRaw !== null && minSharpeRaw !== '') {
    const v = Number(minSharpeRaw);
    if (Number.isFinite(v) && v >= -10 && v <= 10) filters.minLatestSharpe = v;
  }
  // 旧参数 min_weeks（周数）已下线：旧链接落到默认 60%
  if (minPctRaw !== null && minPctRaw !== '') {
    const v = Number(minPctRaw);
    if (Number.isFinite(v) && v >= 0 && v <= 100) filters.minListedPct = Math.round(v);
  }
  if (search.get('latest_only') === '1') filters.latestOnly = true;
  if (rangeRaw && RANGES.has(rangeRaw)) filters.range = rangeRaw as SharpeRange;
  if (pageRaw !== null) {
    const v = Number(pageRaw);
    if (Number.isFinite(v) && v >= 1) filters.page = Math.floor(v);
  }
  if (limitRaw !== null) {
    const v = Number(limitRaw);
    if (Number.isInteger(v) && v >= 1 && v <= 200) filters.limit = v;
  }
  return filters;
}

/** 筛选 → URL 查询串；默认值不写（source/range/page/limit 等省略即默认） */
export function sharpeFiltersToSearch(filters: SharpeBoardFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.source !== DEFAULT_SHARPE_FILTERS.source) params.set('source', filters.source);
  if (filters.profileVersion !== DEFAULT_SHARPE_FILTERS.profileVersion) {
    params.set('profile_version', filters.profileVersion);
  }
  if (filters.minLatestSharpe !== null) params.set('min_latest_sharpe', String(filters.minLatestSharpe));
  if (filters.minListedPct !== DEFAULT_SHARPE_FILTERS.minListedPct) {
    params.set('min_listed_pct', String(filters.minListedPct));
  }
  if (filters.latestOnly) params.set('latest_only', '1');
  if (filters.range !== DEFAULT_SHARPE_FILTERS.range) params.set('range', filters.range);
  if (filters.page !== DEFAULT_SHARPE_FILTERS.page) params.set('page', String(filters.page));
  if (filters.limit !== DEFAULT_SHARPE_FILTERS.limit) params.set('limit', String(filters.limit));
  return params;
}

/** 筛选 → 请求查询串（与 URL 同一套，但始终发 source 保证显式） */
export function sharpeFiltersToQuery(filters: SharpeBoardFilters): string {
  const params = sharpeFiltersToSearch(filters);
  params.set('source', filters.source);
  params.set('profile_version', filters.profileVersion);
  params.set('range', filters.range);
  params.set('page', String(filters.page));
  params.set('limit', String(filters.limit));
  params.set('min_listed_pct', String(filters.minListedPct));
  const q = params.toString();
  return q ? `?${q}` : '';
}

// ─────────────────────────────────────────────────────────────
// 请求（全路径；AbortController 由调用方提供，防旧来源响应覆盖）
// ─────────────────────────────────────────────────────────────

export async function fetchSharpeBoard(
  filters: SharpeBoardFilters,
  signal?: AbortSignal,
): Promise<SharpeBoardResponse> {
  const res = await fetch(`/funds/api/funds/sharpe-board${sharpeFiltersToQuery(filters)}`, {
    cache: 'no-store',
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`请求失败 ${res.status}: ${detail.slice(0, 120)}`);
  }
  return res.json() as Promise<SharpeBoardResponse>;
}

// ─────────────────────────────────────────────────────────────
// 状态分类（R6/R9：首次无数据、成功空榜、展示无匹配可区分；error 由请求层抛出）
// ─────────────────────────────────────────────────────────────

export type SharpeBoardPhase = 'no-data' | 'empty-board' | 'no-match' | 'ok';

/**
 * 判定页面主状态：
 * - no-data：后端从未跑过任何周任务（库空，首次上线）
 * - empty-board：无筛选命中。filtersActive=false 且最新尝试是成功零入选 → 空榜；
 *   其余（全部失败/停机）也是「暂无在榜记录」（失败详情由状态条单独呈现）
 * - no-match：有历史数据但当前展示筛选筛空了
 * - ok：有命中
 */
export function classifySharpeBoard(
  data: SharpeBoardResponse,
  filtersActive: boolean,
): SharpeBoardPhase {
  if (data.latest_attempt === null) return 'no-data';
  if (data.total > 0) return 'ok';
  return filtersActive ? 'no-match' : 'empty-board';
}

/** 展示筛选是否激活（区分「筛选筛空」与「成功空榜」） */
export function sharpeFiltersActive(filters: SharpeBoardFilters): boolean {
  return (
    filters.minLatestSharpe !== null
    || filters.minListedPct !== DEFAULT_SHARPE_FILTERS.minListedPct
    || filters.latestOnly
  );
}

/** 时间范围内是否有任何数据点（无点则图区提示，不造点） */
export function hasPointInRange(series: SharpeBoardSeries[]): boolean {
  return series.some(s => s.values.some(v => v !== null));
}

// ─────────────────────────────────────────────────────────────
// profile 只读文案（入选规则说明 + 市场采集预筛约束说明，R7 透明化）
// ─────────────────────────────────────────────────────────────

/** 从 profile.filters 生成入选条件文案（键名与后端 _ENTRY_FILTERS 对齐） */
export function describeEntryFilters(profile: SharpeBoardProfile): string[] {
  const f = profile.filters;
  const out: string[] = [];
  const num = (v: number | boolean | undefined): number | null =>
    typeof v === 'number' ? v : null;
  const age = num(f.min_age);
  if (age !== null) out.push(`成立 ≥ ${age} 年`);
  const size = num(f.min_size_yi);
  if (size !== null) out.push(`规模 ≥ ${size} 亿`);
  const dd = num(f.max_dd_3y);
  if (dd !== null) out.push(`近三年回撤绝对值 ≤ ${dd}%`);
  const exp = num(f.min_mgr_exp);
  if (exp !== null) out.push(`经理从业 ≥ ${exp} 年`);
  const sharpe = num(f.min_sharpe);
  if (sharpe !== null) out.push(`近三年夏普 ≥ ${sharpe}`);
  // v2 三道新门（11-13 任务）
  const ir = num(f.min_ir);
  if (ir !== null) out.push(`信息比率 IR ≥ ${ir}`);
  const days = num(f.min_sample_days);
  if (days !== null) out.push(`样本交易日 ≥ ${days} 天`);
  // v2 滚动口径
  const peer = num(f.max_peer_pct);
  if (peer !== null) out.push(`近三年同类排名前 ${peer}%`);
  // v3 年度口径（与滚动口径互斥，不会同时出现）
  const yearlyTop = num(f.min_yearly_top_pct);
  const yearlyYears = num(f.min_yearly_years);
  if (yearlyTop !== null && yearlyYears !== null) {
    // 窗口固定 3 个完整年度（不含当年），min_yearly_years 是「其中至少几年达标」
    out.push(`近 3 个完整年度中至少 ${yearlyYears} 年同类排名前 ${yearlyTop}%`);
  }
  if (f.exclude_qdii === true) out.push('排除 QDII');
  return out;
}

/** 市场来源的采集预筛约束文案（空 = 无预筛约束） */
export function describePrefilters(profile: SharpeBoardProfile): string[] {
  const p = profile.collection_prefilters;
  const out: string[] = [];
  if (typeof p.min_ret_3y === 'number') out.push(`近三年收益 ≥ ${p.min_ret_3y}%`);
  if (typeof p.min_size_yi === 'number') out.push(`规模 ≥ ${p.min_size_yi} 亿`);
  if (typeof p.min_mgr_exp === 'number') out.push(`经理从业 ≥ ${p.min_mgr_exp} 年`);
  return out;
}

// ─────────────────────────────────────────────────────────────
// 展示格式化（北京时间，R7 日期真实性）
// ─────────────────────────────────────────────────────────────

/** 周一日期 → MM-DD（同年后缀省略；跨年由调用方展示完整日期） */
export function formatWeekDay(week: string): string {
  return week.length >= 10 ? week.slice(5, 10) : week;
}

/** ISO datetime → 北京时间 MM-DD HH:mm */
export function formatBoardTime(iso: string | null): string {
  if (!iso || Number.isNaN(Date.parse(iso))) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(iso));
}

// ─────────────────────────────────────────────────────────────
// 数据缺口周口径（11-14-sharpe-board-gap-weeks）
//
// 「近52周在榜」= 在榜周数 / 可评周数：分母是窗口内该基金**有有效样本**的周数。
// 数据缺口周（没发榜 / 样本未更新）既不计入在榜，也不打断连续周数——
// 连续段只被「可评却没上榜」的真实缺席打断。
// ─────────────────────────────────────────────────────────────

/** 在榜列文案：在榜/可评（51/51）；可评周数缺失（老后端）→ 只显示在榜周数 */
export function formatListedWeeks(
  listed: number,
  evaluable: number | null | undefined,
): string {
  if (typeof evaluable !== 'number' || evaluable <= 0) return `${listed}`;
  return `${listed}/${evaluable}`;
}

/** 在榜列 tooltip：分母口径 + 该基金的数据缺口周 */
export function listedWeeksTip(
  listed: number,
  evaluable: number | null | undefined,
  gapWeeks: readonly string[] = [],
): string {
  const head =
    typeof evaluable === 'number' && evaluable > 0
      ? `近 52 周在榜 ${listed}/${evaluable}：在榜 ${listed} 周 ÷ 可评 ${evaluable} 周（该基金有有效样本的周数）`
      : `近 52 周在榜 ${listed} 周`;
  if (gapWeeks.length === 0) return head;
  return `${head}；数据缺口周（无榜 / 样本未更新，不计入在榜、也不打断连续）：${gapWeeks.join('、')}`;
}

/** 连续周数列 tooltip：连续段口径 + 该基金的数据缺口周 */
export function consecutiveWeeksTip(
  consecutive: number,
  gapWeeks: readonly string[] = [],
): string {
  const base =
    `最近连续 ${consecutive} 周：从最近上榜周逐周往回数；数据缺口周跳过、不中断，真实缺席（可评却未上榜）才中断`;
  if (gapWeeks.length === 0) return base;
  return `${base}；该基金的数据缺口周：${gapWeeks.join('、')}`;
}
