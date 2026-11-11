/**
 * 收藏跟踪 · 四挡位估值（Hermes stock-four-level-valuation）
 *
 * 契约对齐后端 valuation_service：
 * - 17 字段报告，status ∈ ready/insufficient_data/blocked/not_applicable
 * - 仅 ready 有 levels（四价严格递增）与 valuation；非 ready 两者为 null
 * - per_code 状态 queued/running/cancelling/completed/failed/cancelled（重启清空）
 * 应用走 POST /valuation/{code}/apply（evaluated_at 身份校验），失败/非 ready 永不覆盖旧 alerts。
 */
import type { AlertLevels, RefreshJob } from './types';

export type ValuationStatus = 'ready' | 'insufficient_data' | 'blocked' | 'not_applicable';

/** ready 报告的单挡位（price 必填，pe/pb 来自 skill 计算，可 null） */
export interface ValuationLevelPoint {
  price: number;
  pe: number | null;
  pb: number | null;
}

/** 单股估值报告记录（skill 17 字段 + 后端元数据） */
export interface ValuationReportRecord {
  schema_version: string;
  skill_version: string | null;
  code: string;
  name: string;
  currency: string;
  as_of: string;
  status: ValuationStatus;
  levels: Record<string, ValuationLevelPoint> | null;
  valuation: Record<string, unknown> | null;
  evidence: Array<Record<string, unknown>>;
  data_gaps: string[];
  confidence: { level: string; reason: string } | null;
  risks: string[];
  invalidation_conditions: string[];
  summary: string;
  analysis: Record<string, string>;
  report_md: string;
  evaluated_at: string;
  data_date: string | null;
  analysis_duration_seconds: number | null;
}

export interface ValuationPerCodeItem {
  state: 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled';
  error?: string | null;
  updated_at?: string | null;
  name?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  item_id?: string | null;
  position?: number | null;
}

export type ValuationPerCodeMap = Record<string, ValuationPerCodeItem>;

export interface ValuationStatusResponse {
  total: number;
  reports: Record<string, ValuationReportRecord>;
  per_code: ValuationPerCodeMap;
  hermes_configured: boolean;
  current_skill_version: string | null;
}

export type ValuationJob = RefreshJob & { per_code?: ValuationPerCodeMap; cancelled?: number };

export function isValuationJobActive(job: ValuationJob | null | undefined): boolean {
  return !!job && (job.status === 'queued' || job.status === 'running');
}

export type ValuationMoveAction = 'front' | 'up' | 'down';

export interface ValuationQueueSnapshot {
  per_code: ValuationPerCodeMap;
  running_count: number;
  queued_count: number;
}

/** 是否处于排队/运行/取消中（重复提交禁用、行内「评估中」的判定） */
export function isValuationPending(status?: ValuationPerCodeItem | null): boolean {
  return status?.state === 'queued' || status?.state === 'running' || status?.state === 'cancelling';
}

/** 队列面板行：只含正在评估与排队，排队顺序用服务端 position */
export interface ValuationQueueRow {
  code: string;
  itemId: string | null;
  name: string | null;
  state: ValuationPerCodeItem['state'];
  error: string | null;
  queuedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  position: number | null;
}

export interface ValuationQueueView {
  rows: ValuationQueueRow[];
  runningCount: number;
  queuedCount: number;
}

export function buildValuationQueue(perCode: ValuationPerCodeMap): ValuationQueueView {
  const running: ValuationQueueRow[] = [];
  const queued: ValuationQueueRow[] = [];
  for (const [code, item] of Object.entries(perCode)) {
    const row: ValuationQueueRow = {
      code,
      itemId: item.item_id ?? null,
      name: item.name ?? null,
      state: item.state,
      error: item.error ?? null,
      queuedAt: item.queued_at ?? null,
      startedAt: item.started_at ?? null,
      finishedAt: item.finished_at ?? null,
      position: item.position ?? null,
    };
    if (item.state === 'running' || item.state === 'cancelling') running.push(row);
    else if (item.state === 'queued') queued.push(row);
  }
  queued.sort((a, b) => (a.position ?? Number.MAX_SAFE_INTEGER) - (b.position ?? Number.MAX_SAFE_INTEGER));
  return { rows: [...running, ...queued], runningCount: running.length, queuedCount: queued.length };
}

export const VALUATION_LEVEL_KEYS = ['heavy_position', 'add_position', 'reduce_position', 'full_exit'] as const;
export type ValuationLevelKey = (typeof VALUATION_LEVEL_KEYS)[number];

export const VALUATION_STATUS_LABEL: Record<ValuationStatus, string> = {
  ready: '评估完成',
  insufficient_data: '资料不足',
  blocked: '已阻断',
  not_applicable: '暂不适用',
};

/** 四挡位中文短标签（与生效价格条 ValuationPriceBar 一致） */
export const VALUATION_LEVEL_LABEL: Record<ValuationLevelKey, string> = {
  heavy_position: '重仓',
  add_position: '加仓',
  reduce_position: '减仓',
  full_exit: '全卖',
};

/**
 * 报告 evaluated_at 是否晚于 alerts.updated_at（评估新于当前生效配置 → 待应用）。
 * 双方都是后端 ISO 时间戳；解析失败按「非待应用」处理，不误报。
 */
export function isReportNewerThanAlerts(evaluatedAt: string | null | undefined,
                                        alertsUpdatedAt: string | null | undefined): boolean {
  if (!evaluatedAt) return false;
  if (!alertsUpdatedAt) return true;
  const a = Date.parse(evaluatedAt);
  const b = Date.parse(alertsUpdatedAt);
  if (!Number.isFinite(a)) return false;
  if (!Number.isFinite(b)) return true;
  return a > b;
}

/** 行是否存在生效挡位（alerts 有至少一档价格，无论启用与否） */
export function hasEffectiveLevels(levels: AlertLevels | null | undefined): boolean {
  if (!levels) return false;
  return VALUATION_LEVEL_KEYS.some(key => {
    const lv = levels[key];
    return !!lv && lv.price > 0;
  });
}

/** 报告 levels → AlertLevels 形状（应用对比用） */
export function reportLevelsToAlertLevels(levels: Record<string, ValuationLevelPoint> | null): AlertLevels | null {
  if (!levels) return null;
  const out: AlertLevels = {};
  let count = 0;
  for (const key of VALUATION_LEVEL_KEYS) {
    const point = levels[key];
    if (point && point.price > 0) {
      out[key] = { price: point.price, pe: point.pe ?? null, pb: point.pb ?? null };
      count++;
    }
  }
  return count > 0 ? out : null;
}

/**
 * 单股派生状态（收藏跟踪行）。
 * - monitoring/paused：存在生效挡位（与 alerts.enabled 对应）
 * - pending_apply：ready 报告新于当前配置（可与 monitoring/paused 重叠）
 * - evaluating/failed：per_code 实时状态
 * - not_ready：存在非 ready 报告且无生效挡位
 * - unevaluated：无报告、无任务、无生效挡位
 */
export type FavoriteTrackingState =
  | 'monitoring'
  | 'paused'
  | 'pending_apply'
  | 'evaluating'
  | 'failed'
  | 'not_ready'
  | 'unevaluated';

export interface FavoriteTrackingDerived {
  state: FavoriteTrackingState;
  /** 待应用标志：与 monitoring/paused 可重叠 */
  pendingApply: boolean;
  /** 是否存在生效挡位（无论启用与否） */
  effective: boolean;
  report: ValuationReportRecord | null;
}

export function deriveFavoriteTrackingState(
  alertsEnabled: boolean | undefined,
  alertsLevels: AlertLevels | null | undefined,
  alertsUpdatedAt: string | null | undefined,
  report: ValuationReportRecord | null | undefined,
  perCode: ValuationPerCodeItem | null | undefined,
): FavoriteTrackingDerived {
  const effective = hasEffectiveLevels(alertsLevels);
  const pendingApply = !!report
    && report.status === 'ready'
    && isReportNewerThanAlerts(report.evaluated_at, alertsUpdatedAt);
  const live = perCode?.state;
  let state: FavoriteTrackingState;
  if (effective) {
    state = alertsEnabled ? 'monitoring' : 'paused';
  } else if (live === 'queued' || live === 'running' || live === 'cancelling') {
    state = 'evaluating';
  } else if (live === 'failed') {
    state = 'failed';
  } else if (report) {
    state = report.status === 'ready' ? 'pending_apply' : 'not_ready';
  } else {
    state = 'unevaluated';
  }
  // 有生效挡位时 pending_apply 只作重叠标志，不改变主状态
  return { state: pendingApply && !effective ? 'pending_apply' : state, pendingApply, effective, report: report ?? null };
}

export const TRACKING_STATE_META: Record<FavoriteTrackingState, { label: string; note: string }> = {
  monitoring: { label: '监控中', note: '' },
  paused: { label: '已暂停', note: '挡位保留，未推送提醒' },
  pending_apply: { label: '待应用', note: '确认后开启监控' },
  evaluating: { label: '评估中', note: '正在补充估值依据' },
  failed: { label: '评估失败', note: '可重试' },
  not_ready: { label: '未出价格', note: '未生成价格，可查看原因' },
  unevaluated: { label: '待评估', note: '' },
};

/** 五种筛选的谓词（重叠仅发生在 待应用 ∩ 监控中/已暂停） */
export type TrackingFilterKey = 'all' | 'pending' | 'ready' | 'monitoring' | 'paused';

export function matchesTrackingFilter(filter: TrackingFilterKey, derived: FavoriteTrackingDerived): boolean {
  switch (filter) {
    case 'all':
      return true;
    case 'pending':
      // 待评估：从未应用过挡位（无生效挡位），且当前没有待应用报告
      return !derived.effective
        && !derived.pendingApply
        && (derived.state === 'unevaluated' || derived.state === 'evaluating'
          || derived.state === 'failed' || derived.state === 'not_ready');
    case 'ready':
      return derived.pendingApply;
    case 'monitoring':
      return derived.state === 'monitoring';
    case 'paused':
      return derived.state === 'paused';
    default:
      return false;
  }
}

/** 格式化评估耗时（与 quality 一致的口径），缺失显示 未记录 */
export function formatValuationDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '未记录';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}小时${m}分${s}秒`;
  return `${m}分${s}秒`;
}
