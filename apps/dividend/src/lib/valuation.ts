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
  /** 本次估值的 Hermes run id（session_id 同值）；旧报告可能缺失 */
  run_id?: string | null;
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
  /** 本次分析的 Hermes run id（session_id 同值）；失败时用于下载失败那次的会话记录 */
  run_id?: string | null;
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

/* =====================================================================
 * attempt（最近一次评估尝试）与 report（最新一份可用报告）是两件事
 *
 * 现状把两者揉成一个 derived.state，导致：
 * - 最近一次失败会盖住「待应用」（徽章显示失败，"应用"按钮却指向旧报告）
 * - 报告已应用后 derived.state 仍是 'pending_apply'，语义失真
 *
 * 这里把「最近一次尝试」单独立出来：状态、时间、版本、会话 run_id 四者
 * 永远描述同一次尝试，行内不再出现「下载的是失败那次、时间写的是上次成功那次」。
 * ===================================================================== */

/** 最近一次尝试的状态：none = 从没提交过评估 */
export type ValuationAttemptState =
  | 'none'
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ValuationAttempt {
  /** 最近一次尝试的状态 */
  state: ValuationAttemptState;
  /** 这次尝试的时间：成功=报告评估时间；失败/取消=结束时间；排队=入队时间 */
  at: string | null;
  /** 这次尝试用的 skill 版本（失败/取消那次没有版本可言） */
  skillVersion: string | null;
  /** 这次尝试的 Hermes run id：成功或失败都能下载会话记录 */
  runId: string | null;
  /** 失败原因（仅 failed） */
  error: string | null;
  /** 队列位次（排队中才有，1 起） */
  position: number | null;
  /** 这次尝试对应的报告（成功才有） */
  report: ValuationReportRecord | null;
}

/** 尝试是否仍在进行中（排队/运行/取消中） */
export function isAttemptRunning(state: ValuationAttemptState): boolean {
  return state === 'queued' || state === 'running' || state === 'cancelling';
}

/**
 * 推导最近一次评估尝试。
 *
 * 口径：
 * - per_code 有条目 → 以它为准（它记录的是最近一次尝试，含失败/取消）
 * - per_code 没有条目 → 退回已落盘报告（服务重启后内存队列清空，
 *   只有失败行能从台账并回来；成功的靠报告本身）
 * - 都没有 → 从没评估过
 *
 * 成功那次的版本与时间取自报告：报告就是那次尝试的产物（同一次 run_id）。
 */
export function deriveValuationAttempt(
  report: ValuationReportRecord | null | undefined,
  perCode: ValuationPerCodeItem | null | undefined,
): ValuationAttempt {
  const state = perCode?.state;
  if (!state) {
    // 没有实时条目：有报告就是那次成功尝试的产物
    if (report) {
      return {
        state: 'completed',
        at: report.evaluated_at ?? null,
        skillVersion: report.skill_version ?? null,
        runId: report.run_id ?? null,
        error: null,
        position: null,
        report,
      };
    }
    return { state: 'none', at: null, skillVersion: null, runId: null, error: null, position: null, report: null };
  }
  if (isAttemptRunning(state)) {
    return {
      state,
      at: perCode?.started_at ?? perCode?.queued_at ?? perCode?.updated_at ?? null,
      skillVersion: null,
      runId: perCode?.run_id ?? null,
      error: null,
      position: perCode?.position ?? null,
      report: null,
    };
  }
  if (state === 'failed' || state === 'cancelled') {
    return {
      state,
      at: perCode?.finished_at ?? perCode?.updated_at ?? null,
      skillVersion: null,
      runId: perCode?.run_id ?? null,
      error: perCode?.error ?? null,
      position: null,
      report: null,
    };
  }
  // completed：报告就是这次尝试的产物
  return {
    state: 'completed',
    at: report?.evaluated_at ?? perCode?.finished_at ?? perCode?.updated_at ?? null,
    skillVersion: report?.skill_version ?? null,
    runId: perCode?.run_id ?? report?.run_id ?? null,
    error: null,
    position: null,
    report: report ?? null,
  };
}

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
 *
 * 挡位钉钉推送与监控已移除（2026-11-14）：不再有 monitoring/paused——
 * 那两种状态只反映推送开关，没有开关就没有可派生的含义。
 *
 * 语义修正（2026-11-15）：此前只要存在 ready 报告就置为 'pending_apply'，
 * 哪怕报告早已应用过，语义失真；现在 pending_apply 只在报告确实新于生效挡位时成立。
 * - evaluating：最近一次尝试在跑（queued/running/cancelling）
 * - failed/cancelled：最近一次尝试失败 / 被取消
 * - pending_apply：ready 报告新于当前生效挡位，等你确认应用
 * - not_ready：最近一次尝试出结果，但不是 ready（资料不足/阻断/不适用）
 * - configured：有生效挡位，且没有新于它的报告（等价于「已应用，无事可做」）
 * - unevaluated：从未评估过
 */
export type FavoriteTrackingState =
  | 'configured'
  | 'pending_apply'
  | 'evaluating'
  | 'failed'
  | 'cancelled'
  | 'not_ready'
  | 'unevaluated';

export interface FavoriteTrackingDerived {
  state: FavoriteTrackingState;
  /** 待应用标志：与已有生效挡位可重叠 */
  pendingApply: boolean;
  /** 是否存在生效挡位（无论启用与否） */
  effective: boolean;
  report: ValuationReportRecord | null;
}

/**
 * 评估状态（只讲评估本身，与 alerts.enabled 无关）。
 *
 * 列表状态列只讲评估——推送与监控已整体移除（2026-11-14）；
 * 两者挤在一格会让人以为「暂停 = 没评估」。监控开关仍在「挡位设置」里。
 *
 * 语义修正（2026-11-15）：状态讲的是「最近一次尝试」，不再与「可用报告」混为一谈——
 * 最近一次失败时，即使还留着一份待应用的旧报告，徽章也要说失败（旧报告另由挡位列与操作列表达）。
 * - unevaluated：从未评估过（无报告、无在跑记录、无生效挡位）
 * - manual：只有手工挡位，从没走过 Hermes 估值
 * - evaluating：queued/running/cancelling
 * - failed：最近一次评估失败
 * - cancelled：最近一次评估被取消
 * - not_ready：出过结果但状态不是 ready（资料不足/阻断/不适用）
 * - succeeded：有 ready 报告且没有更新的待应用报告
 * - pending_apply：ready 报告新于生效挡位，等待确认应用
 */
export type ValuationEvalState =
  | 'unevaluated'
  | 'manual'
  | 'evaluating'
  | 'failed'
  | 'cancelled'
  | 'not_ready'
  | 'succeeded'
  | 'pending_apply';

export const VALUATION_EVAL_STATE_META: Record<ValuationEvalState, { label: string; tone: 'ok' | 'warn' | 'bad' | 'idle' }> = {
  succeeded: { label: '评估完成', tone: 'ok' },
  pending_apply: { label: '待应用', tone: 'warn' },
  evaluating: { label: '评估中', tone: 'idle' },
  failed: { label: '评估失败', tone: 'bad' },
  cancelled: { label: '已取消', tone: 'idle' },
  not_ready: { label: '未出价格', tone: 'idle' },
  manual: { label: '手工挡位', tone: 'idle' },
  unevaluated: { label: '待评估', tone: 'idle' },
};

/**
 * 推导评估状态：讲「最近一次尝试」，不再与「可用报告」混为一谈。
 *
 * 「失败/取消」优先于旧的成功报告：最近一次尝试没成，列表要说没成，
 * 而不是拿旧报告冒充成功；旧报告另由挡位列与操作列表达（仍可查看/应用）。
 */
export function deriveValuationEvalState(
  derived: FavoriteTrackingDerived,
  perCode: ValuationPerCodeItem | null | undefined,
): ValuationEvalState {
  const attempt = deriveValuationAttempt(derived.report, perCode);
  if (isAttemptRunning(attempt.state)) return 'evaluating';
  if (attempt.state === 'failed') return 'failed';
  if (attempt.state === 'cancelled') return 'cancelled';
  if (derived.report) {
    if (derived.report.status !== 'ready') return 'not_ready';
    return derived.pendingApply ? 'pending_apply' : 'succeeded';
  }
  // 没有任何 Hermes 评估痕迹：手工挡位 or 从没评估
  return derived.effective ? 'manual' : 'unevaluated';
}


export function deriveFavoriteTrackingState(
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
  if (live === 'queued' || live === 'running' || live === 'cancelling') {
    state = 'evaluating';
  } else if (live === 'failed') {
    state = 'failed';
  } else if (live === 'cancelled') {
    state = 'cancelled';
  } else if (pendingApply) {
    state = 'pending_apply';
  } else if (report) {
    // 有报告但没有更新的待应用报告：已应用（或报告比生效挡位旧）
    state = report.status === 'ready' ? 'configured' : 'not_ready';
  } else if (effective) {
    state = 'configured';
  } else {
    state = 'unevaluated';
  }
  return { state, pendingApply, effective, report: report ?? null };
}

/* =====================================================================
 * 行内动作推导
 *
 * 一行的动作由三个事实共同决定：
 * - attempt（最近一次尝试）：决定「评估 / 重试 / 再评估 / 评估中」
 * - report（最新一份可用报告）：决定「查看报告 / 查看缺口」
 * - pendingApply：决定「应用」
 *
 * 关键修正：失败与待应用可以并存，两件事都要露出——
 * 现状 pendingApply 优先命中「应用」，把「重试评估」挤掉了。
 * ===================================================================== */

/** 行内「评估」按钮的种类 */
export type TrackingEvaluateAction = 'none' | 'running' | 'evaluate' | 'retry' | 'reevaluate';

/** 行内次要链接 */
export type TrackingLink = 'view_report' | 'view_gaps' | 'settings';

export interface TrackingActions {
  /** 评估类按钮（评估挡位 / 重试评估 / 再评估 / 评估中） */
  evaluate: TrackingEvaluateAction;
  /** 是否给「应用」按钮（有更新的待应用报告时） */
  apply: boolean;
  /** 次要链接（查看报告 / 查看缺口 / 挡位设置） */
  links: TrackingLink[];
}

/**
 * 推导行内动作。
 *
 * - 从没提交过评估 → 「评估挡位」
 * - 最近一次失败 → 「重试评估」（失败原因由评估状态列承载）
 * - 最近一次取消 → 「再评估」
 * - 已成功评估过（有报告）→ 「再评估」
 * - 有更新的待应用报告 → 额外给「应用」
 * - 有报告 → 给「查看报告」（非 ready 报告给「查看缺口」）
 */
export function deriveTrackingActions(
  attempt: ValuationAttempt,
  derived: FavoriteTrackingDerived,
): TrackingActions {
  const report = derived.report;
  const evaluate: TrackingEvaluateAction = isAttemptRunning(attempt.state) ? 'running'
    : attempt.state === 'failed' ? 'retry'
    : attempt.state === 'none' ? 'evaluate'
    : 'reevaluate';
  const links: TrackingLink[] = [];
  if (report) links.push(report.status === 'ready' ? 'view_report' : 'view_gaps');
  links.push('settings');
  return { evaluate, apply: derived.pendingApply, links };
}


export const TRACKING_STATE_META: Record<FavoriteTrackingState, { label: string; note: string }> = {
  configured: { label: '已配置挡位', note: '' },
  pending_apply: { label: '待应用', note: '确认后使用新挡位' },
  evaluating: { label: '评估中', note: '正在补充估值依据' },
  failed: { label: '评估失败', note: '可重试' },
  cancelled: { label: '已取消', note: '本次评估被取消，可重新评估' },
  not_ready: { label: '未出价格', note: '未生成价格，可查看原因' },
  unevaluated: { label: '待评估', note: '' },
};

/** 三种筛选的谓词（推送与监控已移除，不再有按启停状态的筛选） */
export type TrackingFilterKey = 'all' | 'pending' | 'ready';

export function matchesTrackingFilter(filter: TrackingFilterKey, derived: FavoriteTrackingDerived): boolean {
  switch (filter) {
    case 'all':
      return true;
    case 'pending':
      // 待评估：还没出过可用价格（无生效挡位、无待应用报告），需要再评估一次
      return !derived.effective
        && !derived.pendingApply
        && (derived.state === 'unevaluated' || derived.state === 'evaluating'
          || derived.state === 'failed' || derived.state === 'cancelled' || derived.state === 'not_ready');
    case 'ready':
      return derived.pendingApply;
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

/** 现价所处的五分区（与 ValuationPriceBar 的区间划分同一口径） */
export type ValuationZone = 'heavy' | 'add' | 'hold' | 'reduce' | 'full';

export const VALUATION_ZONE_LABEL: Record<ValuationZone, string> = {
  heavy: '重仓区',
  add: '加仓区',
  hold: '持有区',
  reduce: '减仓区',
  full: '全卖区',
};

/** 五区间色（价格条色带与「区间」列共用，单一来源） */
export const VALUATION_ZONE_COLOR: Record<ValuationZone, string> = {
  heavy: '#5A9472',
  add: '#C9951F',
  hold: '#D9D2C2',
  reduce: '#D4893A',
  full: '#9B2F2F',
};

/** 区间名文字色：持有区底色太浅，文字走中性色保证对比度 */
export const VALUATION_ZONE_TEXT_COLOR: Record<ValuationZone, string> = {
  heavy: VALUATION_ZONE_COLOR.heavy,
  add: VALUATION_ZONE_COLOR.add,
  hold: '#6B6864',
  reduce: VALUATION_ZONE_COLOR.reduce,
  full: VALUATION_ZONE_COLOR.full,
};

/** 告警档位文案（对齐后端 AlertService 的 LEVEL_META） */
export const VALUATION_ALERT_LABEL: Record<ValuationLevelKey, string> = {
  heavy_position: '可加仓',
  add_position: '加仓价位',
  reduce_position: '该减仓',
  full_exit: '全部清仓',
};

export interface ValuationZoneResult {
  /** 现价所在区间；档位不足四条时判不出（null） */
  zone: ValuationZone | null;
  /** 命中的告警档位（持有区不命中） */
  hitKey: ValuationLevelKey | null;
  hitLabel: string | null;
  hitPrice: number | null;
  /** 距命中档位线的百分比（后端 distance_pct 同口径，可正可负） */
  distancePct: number | null;
  /** 是否会触发提醒 */
  willTrigger: boolean;
}

/**
 * 现价落在挡位的哪一区、会不会触发提醒。
 *
 * 区间口径与 ValuationPriceBar.currentSegSide 一致（四条线重仓<加仓<减仓<全卖）：
 * ≤重仓=重仓区、≤加仓=加仓区、≤减仓=持有区、≤全卖=减仓区、>全卖=全卖区。
 * 命中判定严格复刻后端 AlertService._find_hit_level：先卖后买、severity 高者优先，
 * 持有区两边都不命中（不推提醒）。
 */
export function resolveValuationZone(
  levels: AlertLevels | null | undefined,
  price: number | null | undefined,
): ValuationZoneResult {
  const empty: ValuationZoneResult = {
    zone: null, hitKey: null, hitLabel: null, hitPrice: null, distancePct: null, willTrigger: false,
  };
  if (!levels || price == null || !(price > 0)) return empty;

  const points = VALUATION_LEVEL_KEYS
    .map(key => ({ key, price: levels[key]?.price }))
    .filter((p): p is { key: ValuationLevelKey; price: number } => p.price != null && p.price > 0);
  // 不足四条线判不出区间（手工配置可能只填一档）
  if (points.length !== VALUATION_LEVEL_KEYS.length) return empty;

  const sorted = [...points].sort((a, b) => a.price - b.price);
  const [heavy, add, reduce, full] = sorted;

  const zone: ValuationZone = price <= heavy.price ? 'heavy'
    : price <= add.price ? 'add'
      : price <= reduce.price ? 'hold'
        : price <= full.price ? 'reduce'
          : 'full';

  // 命中判定：卖出方向（减仓/全卖）优先于买入方向（加仓/重仓），同向取 severity 高者
  const sellHits = points
    .filter(p => (p.key === 'reduce_position' || p.key === 'full_exit') && price >= p.price)
    .sort((a, b) => severity(b.key) - severity(a.key));
  const buyHits = points
    .filter(p => (p.key === 'heavy_position' || p.key === 'add_position') && price <= p.price)
    .sort((a, b) => severity(b.key) - severity(a.key));
  const hit = sellHits[0] ?? buyHits[0] ?? null;

  return {
    zone,
    hitKey: hit?.key ?? null,
    hitLabel: hit ? VALUATION_ALERT_LABEL[hit.key] : null,
    hitPrice: hit?.price ?? null,
    distancePct: hit ? ((price - hit.price) / hit.price) * 100 : null,
    willTrigger: !!hit,
  };
}

/** 告警 severity（对齐后端 LEVEL_META） */
function severity(key: ValuationLevelKey): number {
  return key === 'heavy_position' || key === 'full_exit' ? 2 : 1;
}

/** 「再走多远会改变告警动作」的一步：目标价位线 + 方向 + 按现价算的百分比 */
export interface ValuationZoneStep {
  key: ValuationLevelKey;
  price: number;
  /** up = 还要涨才够到该线；down = 还要跌 */
  direction: 'up' | 'down';
  /** 距该线的百分比（绝对值；0 表示正好踩线） */
  pct: number;
}

/**
 * 现价沿「改变告警动作」的方向，到下一个会变盘的价位线还有多远。
 *
 * 与区间一一对应（口径同 resolveValuationZone）：
 * - 重仓区：涨回重仓线 → 不再是「可加仓」（1 步，↑）
 * - 加仓区：跌回重仓线 → 升为「可加仓」（1 步，↓）
 * - 持有区：上下各一条改变动作的线 → 涨到减仓「该减仓」、跌到加仓「加仓价位」（2 步）
 * - 减仓区：涨到全卖线 → 「全部清仓」（1 步，↑）
 * - 全卖区：跌回全卖线 → 降级为「该减仓」（1 步，↓）
 *
 * 档位不足四条时判不出（返回空数组）。
 */
export function resolveZoneSteps(
  levels: AlertLevels | null | undefined,
  price: number | null | undefined,
): ValuationZoneStep[] {
  if (!levels || price == null || !(price > 0)) return [];

  const points = VALUATION_LEVEL_KEYS
    .map(key => ({ key, price: levels[key]?.price }))
    .filter((p): p is { key: ValuationLevelKey; price: number } => p.price != null && p.price > 0);
  if (points.length !== VALUATION_LEVEL_KEYS.length) return [];

  const sorted = [...points].sort((a, b) => a.price - b.price);
  const [heavy, add, reduce, full] = sorted;
  const step = (point: typeof heavy, direction: ValuationZoneStep['direction']): ValuationZoneStep => ({
    key: point.key,
    price: point.price,
    direction,
    pct: Math.abs((point.price - price) / price) * 100,
  });

  if (price <= heavy.price) return [step(heavy, 'up')];
  if (price <= add.price) return [step(heavy, 'down')];
  if (price <= reduce.price) return [step(reduce, 'up'), step(add, 'down')];
  if (price <= full.price) return [step(full, 'up')];
  return [step(full, 'down')];
}
