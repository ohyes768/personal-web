// 租金与收益契约（design.md "Query API" 定稿）。
// 后端路由 GET /api/communities/{id}/rentals，nginx 对外前缀 /api/map/。
// 数值缺失一律 null，不出现 NaN/Infinity。

export type RentalAvailability =
  | 'available'
  | 'unmapped'
  | 'no_samples'
  | 'insufficient_samples'
  | 'stale'
  | 'source_failed';

export type RentalAreaBand = 'all' | 'lt90' | '90to144' | 'gte144';
export type RentalBedroomsFilter = 'all' | '1' | '2' | '3' | '4plus';
export type SalePriceKind = 'signed' | 'listing';
export type RentalSampleView = 'valid' | 'excluded';

export interface RentReference {
  /** 组内月租中位数（元/月） */
  median_month_rent_yuan: number | null;
  /** 逐房源 月租/面积 的中位数（元/㎡/月） */
  median_unit_rent_yuan_m2_month: number | null;
  /** 单位租金 P25（元/㎡/月） */
  p25_unit_rent_yuan_m2_month: number | null;
  /** 单位租金 P75（元/㎡/月） */
  p75_unit_rent_yuan_m2_month: number | null;
  /** 参与该组统计的合格样本数 */
  sample_count: number;
}

export interface SaleReference {
  /** 有效售价单价（元/㎡），来自现有价格快照策略 */
  unit_price_yuan_m2: number | null;
  /** 售价口径：signed=近期签约价，listing=挂牌价 */
  price_kind: SalePriceKind | null;
  /** 售价口径对应的价格日期 */
  price_date: string | null;
}

export interface YieldEstimate {
  /** 参考年化毛收益率（%）：unit_rent * 12 / sale_unit_price * 100 */
  annualized_gross_yield_pct: number | null;
  /** 月租售比 1:N，N = sale_unit_price / unit_rent */
  rent_to_sale_ratio: number | null;
}

export interface RentalGroup {
  /** 卧室数；null 表示"全部房型"在该面积段合并重算的口径 */
  bedrooms: number | null;
  area_band: Exclude<RentalAreaBand, 'all'>;
  sample_count: number;
  /** 组样本 < 3 时为 null（只展示明细，不输出组参考值） */
  rent_reference: RentReference | null;
  sale_reference: SaleReference | null;
  /** stale 或缺有效售价时为 null */
  yield_estimate: YieldEstimate | null;
}

export interface RentalSample {
  source_listing_id: string;
  title: string | null;
  bedrooms: number | null;
  area_m2: number | null;
  /** 挂牌月租（元/月） */
  month_rent_yuan: number | null;
  /** 月租/面积（元/㎡/月） */
  unit_rent_yuan_m2_month: number | null;
  source_url: string | null;
  captured_at: string | null;
}

export interface RentalDetailSample extends RentalSample {
  /** view=excluded 时的排除理由；有效样本为 null */
  exclude_reason?: string | null;
}

export interface RentalLastRefresh {
  status: 'ok' | 'failed' | 'running' | 'cancelled';
  finished_at: string | null;
  error: string | null;
}

export interface RentalDetailData {
  regional_sample?: boolean;
  availability: RentalAvailability;
  /** 最近一次采集任务结果；允许"旧数据可用 + 最近抓取失败"并存 */
  last_refresh: RentalLastRefresh | null;
  /** 有效候选样本数 */
  sample_count: number;
  /** 被排除样本数（含排除理由） */
  excluded_count: number;
  /** 当前发布版本对应的租金采集时间 */
  captured_at: string | null;
  groups: RentalGroup[];
  /** 小区房型分布，键为卧室数（'1'/'2'/…），值为该房型样本数 */
  bedrooms_distribution: Record<string, number>;
  /** 明细分页；默认有效候选，view=excluded 时每项带 exclude_reason */
  samples: RentalDetailSample[];
  page: number;
  page_size: number;
  total: number;
  /** 来源链接（后端已限定预期来源域，前端渲染前仍做域校验） */
  source_links: string[];
}

// ---- 刷新任务（GET/POST/DELETE /api/rentals/refresh，design.md "Web refresh"）----

export type RentalRefreshPhase =
  | 'running'
  | 'cancelling'
  | 'succeeded'
  | 'partial_failed'
  | 'failed'
  | 'cancelled'
  | 'interrupted';

export interface RentalRefreshError {
  community_id: string | null;
  message: string;
}

export interface RentalRefreshResult {
  published: boolean;
  success_count: number;
  failed_count: number;
}

export interface RentalAssociationProgress {
  targets: number; excluded: number; checked: number; matched: number; pending: number; skipped: number; missing: number; failed: number;
  deferred?: number;
}

export interface RentalRequestDiagnostics {
  request_count?: number;
  detail_cache_hits?: number;
  reused_communities?: number;
  deferred_count?: number;
  cooldown_until?: string | null;
  new_sources_deferred?: number;
}

export interface RentalRefreshJob extends RentalRequestDiagnostics {
  stage?: string | null;
  association?: RentalAssociationProgress | null;
  job_id: string;
  running: boolean;
  phase: RentalRefreshPhase;
  total_communities: number;
  processed_communities: number;
  current_community_id: string | null;
  pages_fetched: number;
  details_fetched: number;
  success_count: number;
  failed_count: number;
  started_at: string | null;
  finished_at: string | null;
  last_success_at: string | null;
  /** errors.items 有条数上限，total 为真实失败总数 */
  errors: { items: RentalRefreshError[]; total: number };
  result: RentalRefreshResult | null;
}

/** 终态集合与判定独立成纯函数，便于轮询逻辑测试与复用 */
export const RENTAL_TERMINAL_PHASES: readonly RentalRefreshPhase[] = [
  'succeeded',
  'partial_failed',
  'failed',
  'cancelled',
  'interrupted',
];

export function isTerminalPhase(phase: RentalRefreshPhase): boolean {
  return RENTAL_TERMINAL_PHASES.includes(phase);
}

// ---- 请求路径与取数 ----

export interface RentalDetailQuery {
  areaBand: RentalAreaBand;
  bedrooms: RentalBedroomsFilter;
  page: number;
  view: RentalSampleView;
}

export const RENTAL_DETAIL_PAGE_SIZE = 10;

export function buildRentalDetailPath(communityId: string, query: RentalDetailQuery): string {
  const params = new URLSearchParams({
    area_band: query.areaBand,
    bedrooms: query.bedrooms,
    view: query.view,
    page: String(query.page),
    page_size: String(RENTAL_DETAIL_PAGE_SIZE),
  });
  return `communities/${encodeURIComponent(communityId)}/rentals?${params.toString()}`;
}

export async function fetchRentalData<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/map/${path}`, { signal });
  if (!response.ok) throw new Error('租金数据暂时不可用');
  const payload: unknown = await response.json();
  if (!isEnvelope<T>(payload)) throw new Error('租金数据响应异常');
  return payload.data;
}

function isEnvelope<T>(payload: unknown): payload is { success: true; data: T } {
  if (typeof payload !== 'object' || payload === null) return false;
  const candidate = payload as { success?: unknown; data?: unknown };
  return candidate.success === true && candidate.data !== undefined && candidate.data !== null;
}

// ---- 看板摘要（GET /api/rentals/summary?area_band=...&bedrooms=...，design.md "Query API"）----
// 与详情接口同一统计算法，按内部 community_id 返回统一口径摘要，供看板独立加载。

export interface RentalSummaryEntry {
  community_id: string;
  availability: RentalAvailability;
  /** 允许"旧数据可用 + 最近抓取失败"并存 */
  last_refresh: RentalLastRefresh | null;
  /** 该口径下有效候选样本数 */
  sample_count: number;
  /** 当前发布版本对应的租金采集时间 */
  captured_at: string | null;
  /** 该口径单位租金中位数（元/㎡/月）；样本不足 3 条或无样本为 null */
  unit_rent_yuan_m2_month: number | null;
  /** 参考年化毛收益率（%）；stale 或缺有效售价为 null */
  annualized_gross_yield_pct: number | null;
}

export interface RentalSummaryData {
  area_band: RentalAreaBand;
  bedrooms: RentalBedroomsFilter;
  summaries: RentalSummaryEntry[];
}

export function buildRentalSummaryPath(query: {
  areaBand: RentalAreaBand;
  bedrooms: RentalBedroomsFilter;
}): string {
  const params = new URLSearchParams({
    area_band: query.areaBand,
    bedrooms: query.bedrooms,
  });
  return `rentals/summary?${params.toString()}`;
}

// ---- 刷新任务取数（nginx 对外路径 /api/map/rentals/refresh）----

function isRefreshEnvelope(payload: unknown): payload is { success: true; data: RentalRefreshJob | null } {
  if (typeof payload !== 'object' || payload === null) return false;
  const candidate = payload as { success?: unknown; data?: unknown };
  return candidate.success === true;
}

/** GET：无活动任务时后端返回 data=null */
export async function fetchRentalRefreshJob(signal?: AbortSignal): Promise<RentalRefreshJob | null> {
  const response = await fetch('/api/map/rentals/refresh', { signal });
  if (!response.ok) throw new Error('租金更新状态暂时不可用');
  const payload: unknown = await response.json();
  if (!isRefreshEnvelope(payload)) throw new Error('租金更新状态响应异常');
  return payload.data;
}

/** POST：202 启动；409 已有任务；422 无可采集映射 */
export async function startRentalRefresh(signal?: AbortSignal): Promise<RentalRefreshJob> {
  const response = await fetch('/api/map/rentals/refresh', { method: 'POST', signal });
  if (response.status === 409) throw new Error('已有租金更新任务在运行，请稍后再试');
  if (response.status === 422) throw new Error('还没有关联租金来源，请先选择小区并确认来源');
  if (!response.ok) throw new Error('租金更新服务暂时不可用');
  const payload: unknown = await response.json();
  if (!isRefreshEnvelope(payload) || payload.data === null) throw new Error('租金更新响应异常');
  return payload.data;
}

/** DELETE：设置取消事件；无活动任务返回 409 */
export async function cancelRentalRefresh(signal?: AbortSignal): Promise<RentalRefreshJob> {
  const response = await fetch('/api/map/rentals/refresh', { method: 'DELETE', signal });
  if (response.status === 409) throw new Error('当前没有正在运行的租金更新任务');
  if (!response.ok) throw new Error('租金更新服务暂时不可用');
  const payload: unknown = await response.json();
  if (!isRefreshEnvelope(payload) || payload.data === null) throw new Error('租金更新响应异常');
  return payload.data;
}
