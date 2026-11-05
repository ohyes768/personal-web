// 价格时效与刷新状态的读取侧归一化（11-04-housing-price-freshness）。
//
// 后端契约（见任务 design.md / backend price_policy.py）:
// - 每条价格条目: {price, month, captured_at, source_url, stale}; API 实际不透出
//   captured_date/current/expired, 采集日从 captured_at 截取, 过期与否由槽位决定
//   (history_deal 槽内必为过期签约)。
// - counts 套数带独立采集时间; 旧快照只有兼容 listing_count/deal_count, 无时间。
// - job 轮级统计键是 camelCase(noData), outcome 枚举是 snake_case(no_data)。
//
// 这里是唯一读取口: 缺失字段不崩、不编造未知字段; 弹窗/看板/刷新控件都消费
// 本层的归一化结果, 避免"每个消费方各自解析一份 payload"。

import type { PriceInfo } from './types';

// ---------------------------------------------------------------------------
// 价格条目
// ---------------------------------------------------------------------------

export interface NormalizedPriceEntry {
  price: number;
  month: string | null;        // 价格所属月份 "YYYY-MM"; 挂牌价恒为 null
  capturedAt: string | null;   // 采集时间原样透传
  capturedDate: string | null; // 采集日 YYYY-MM-DD (captured_at 截前 10 位)
  sourceUrl: string | null;
  stale: boolean;              // 超过 30 天未成功更新
  expired: boolean;            // 成交月份超过 6 个月 (history_deal 槽恒 true)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

// ISO 时间戳/日期字符串 → "YYYY-MM-DD"; 无法判定返回 null, 不编造
export function shortDate(value: unknown): string | null {
  const text = stringValue(value);
  return text ? text.slice(0, 10) : null;
}

// "YYYY-MM" → "2026年10月"; 非月份字符串返回 null (未知月份不得用采集日期顶替)
export function monthLabel(month: unknown): string | null {
  const text = stringValue(month);
  if (!text || !/^\d{4}-\d{2}$/.test(text)) return null;
  const monthNumber = Number(text.slice(5, 7));
  if (monthNumber < 1 || monthNumber > 12) return null;
  return `${text.slice(0, 4)}年${monthNumber}月`;
}

export function normalizePriceEntry(raw: unknown, expired = false): NormalizedPriceEntry | null {
  if (!isRecord(raw)) return null;
  const price = finiteNumber(raw.price);
  if (price == null) return null;
  const capturedAt = stringValue(raw.captured_at);
  return {
    price,
    month: stringValue(raw.month),
    capturedAt,
    capturedDate: shortDate(raw.captured_date) ?? shortDate(capturedAt),
    sourceUrl: stringValue(raw.source_url),
    stale: raw.stale === true,
    expired: raw.expired === true || expired,
  };
}

// 兼容形状 (只读 deal_avg_price/listing_avg_price + snapshot_date 的旧快照):
// 月份未知保持 null; 陈旧无法判定不算陈旧 (与后端 collection_stale 同语义);
// 快照日是旧数据唯一可用的时间, 作为采集日透传, 不作额外的编造。
function compatPriceEntry(value: unknown, snapshotDate: unknown): NormalizedPriceEntry | null {
  const price = finiteNumber(value);
  if (price == null || price <= 0) return null;
  return {
    price,
    month: null,
    capturedAt: typeof snapshotDate === 'string' && snapshotDate ? snapshotDate : null,
    capturedDate: shortDate(snapshotDate),
    sourceUrl: null,
    stale: false,
    expired: false,
  };
}

// ---------------------------------------------------------------------------
// 套数与每小区刷新状态
// ---------------------------------------------------------------------------

export interface NormalizedCounts {
  listingCount: number | null;
  dealCount: number | null;
  capturedAt: string | null; // 套数自己的采集时间, 与价格采集时间独立
}

export interface NormalizedRefreshStatus {
  outcome: string;                  // updated | no_data | failed | skipped (snake_case 枚举)
  partial: boolean;
  retained: boolean;
  retainedReason: string | null;
  retainedPriceDate: string | null;
  priceUpdated: boolean;
  countsUpdated: boolean;
  priceCapturedAt: string | null;
  countsCapturedAt: string | null;
  updatedAt: string | null;
  mode: string | null;
}

export interface NormalizedPriceBlock {
  deal: NormalizedPriceEntry | null;
  listing: NormalizedPriceEntry | null;
  historyDeal: NormalizedPriceEntry | null; // 过期签约, 仅历史参考
  counts: NormalizedCounts;
  refresh: NormalizedRefreshStatus | null;
  hasCurrentPrice: boolean;         // 有任一当前有效价 (deal 或 listing)
}

// 套数读取: 新 counts 槽优先, 兼容旧快照的顶层 listing_count/deal_count。
// 兼容路径没有独立采集时间, capturedAt 保持 null, 不拿价格采集日冒充。
function normalizeCounts(price: Record<string, unknown>): NormalizedCounts {
  const slot = isRecord(price.counts) ? price.counts : null;
  if (slot) {
    return {
      listingCount: finiteNumber(slot.listing_count),
      dealCount: finiteNumber(slot.deal_count),
      capturedAt: stringValue(slot.captured_at),
    };
  }
  return {
    listingCount: finiteNumber(price.listing_count),
    dealCount: finiteNumber(price.deal_count),
    capturedAt: null,
  };
}

// 每小区刷新状态: 必须带字符串 outcome 才算有效 (与后端读取规则一致), 否则 null
function normalizeRefreshStatus(raw: unknown): NormalizedRefreshStatus | null {
  if (!isRecord(raw) || typeof raw.outcome !== 'string') return null;
  return {
    outcome: raw.outcome,
    partial: raw.partial === true,
    retained: raw.retained === true,
    retainedReason: stringValue(raw.retained_reason),
    retainedPriceDate: shortDate(raw.retained_price_date),
    priceUpdated: raw.price_updated === true,
    countsUpdated: raw.counts_updated === true,
    priceCapturedAt: stringValue(raw.price_captured_at),
    countsCapturedAt: stringValue(raw.counts_captured_at),
    updatedAt: stringValue(raw.updated_at),
    mode: stringValue(raw.mode),
  };
}

export function normalizePriceBlock(price: PriceInfo | null | undefined): NormalizedPriceBlock {
  // 读取侧有意按动态 payload 处理: 字段缺失/形状不符都不崩, 归一化后再消费
  const raw: Record<string, unknown> = isRecord(price) ? price : {};
  let deal = normalizePriceEntry(raw.deal);
  let listing = normalizePriceEntry(raw.listing);
  // history_deal 槽位内的签约必为过期价 (后端按 expired 分槽), 槽位即证据
  const historyDeal = normalizePriceEntry(raw.history_deal, true);
  // 兼容旧快照: 新槽位缺失但兼容字段有有效价时回退。旧数据没有所属月份,
  // month 保持 null (界面如实显示"月份未知"), 不拿快照日顶替月份。
  if (deal == null) deal = compatPriceEntry(raw.deal_avg_price, raw.snapshot_date);
  if (listing == null) listing = compatPriceEntry(raw.listing_avg_price, raw.snapshot_date);
  return {
    deal,
    listing,
    historyDeal,
    counts: normalizeCounts(raw),
    refresh: normalizeRefreshStatus(raw.refresh),
    hasCurrentPrice: deal != null || listing != null,
  };
}

// ---------------------------------------------------------------------------
// 展示格式化
// ---------------------------------------------------------------------------

export const STALE_HINT = '超过30天未更新';

export interface DualPriceLine {
  tag: '签' | '挂';
  text: string;            // 数值文案 (千分位) 或 '—'
  meta: string | null;     // 签约价=所属月份; 挂牌价=采集日; 缺失为 null
  stale: boolean;
  missing: boolean;
  title: string;           // 悬浮说明: 口径 + 采集日 + 陈旧/缺失原因
}

// 看板与弹窗共用的双价行: 签约/挂牌各一行, 互不隐藏 (R2)。
// 签约行 meta 是价格所属月份; 挂牌行没有成交月份概念, meta 用采集日。
export function dualPriceLines(block: NormalizedPriceBlock): DualPriceLine[] {
  const lineOf = (tag: '签' | '挂', entry: NormalizedPriceEntry | null, kind: string): DualPriceLine => {
    if (entry == null) {
      return {
        tag,
        text: '—',
        meta: null,
        stale: false,
        missing: true,
        title: `暂无有效${kind}`,
      };
    }
    const meta = tag === '签' ? monthLabel(entry.month) : entry.capturedDate;
    const parts = [`${kind} ${entry.price.toLocaleString()} 元/㎡`];
    if (tag === '签' && monthLabel(entry.month)) parts.push(`价格所属月份 ${monthLabel(entry.month)}`);
    parts.push(entry.capturedDate ? `${entry.capturedDate} 采集` : '采集时间未知');
    if (entry.stale) parts.push(STALE_HINT);
    return {
      tag,
      text: entry.price.toLocaleString(),
      meta,
      stale: entry.stale,
      missing: false,
      title: parts.join('；'),
    };
  };
  return [
    lineOf('签', block.deal, '签约均价'),
    lineOf('挂', block.listing, '挂牌均价'),
  ];
}

// 每小区刷新状态的一句话说明; null 表示没有状态可说, 不编造
export function refreshStatusLine(refresh: NormalizedRefreshStatus | null): string | null {
  if (refresh == null) return null;
  const parts: string[] = [];
  if (refresh.outcome === 'skipped') {
    // skipped 小区不计 retained (R5), 资格在轮内变化被跳过
    parts.push('本轮资格变化，已跳过采集');
  } else if (refresh.priceUpdated) {
    parts.push('本轮价格已更新');
    if (refresh.partial) parts.push('部分页面失败');
  } else if (refresh.countsUpdated) {
    // 套数更新不能说成价格更新 (R3)
    parts.push('本轮仅更新套数，价格未更新');
  } else if (refresh.outcome === 'failed') {
    parts.push('本轮采集失败');
  } else if (refresh.outcome === 'no_data') {
    parts.push('本轮无可用价格数据');
  } else {
    parts.push('本轮价格未更新');
  }
  if (refresh.retained && refresh.retainedPriceDate) {
    const reason = refresh.retainedReason ? `（${retainedReasonLabel(refresh.retainedReason)}）` : '';
    parts.push(`保留 ${refresh.retainedPriceDate} 价格${reason}`);
  }
  return parts.join(' · ');
}

export function retainedReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    fetch_failed: '抓取失败',
    parse_failed: '解析失败',
    no_price_data: '无价格数据',
    expired_only: '仅抓到过期价格',
    ineligible: '资格变化',
  };
  return labels[reason] ?? reason;
}

// ---------------------------------------------------------------------------
// 刷新任务 (GET /api/map/refresh 的 data)
// ---------------------------------------------------------------------------

export interface RefreshResultView {
  outcome: string;        // succeeded | partial | failed | no_data | skipped
  published: boolean;     // 主快照是否发布过
  warnings: string[];
}

export interface RefreshJobView {
  running: boolean;
  phase: string;          // idle | fetching | merging | done | error | cancelled
  mode: 'all' | 'missing' | null;
  total: number;
  processed: number;
  updated: number;        // 有效更新 (兼容 okCount)
  noData: number;         // 无可用数据
  failed: number;         // 失败 (兼容 errorCount)
  skipped: number;        // 资格变化跳过
  retained: number;       // 保留旧价 (可与前三类重叠)
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  result: RefreshResultView | null;
}

function countValue(value: unknown): number {
  return finiteNumber(value) ?? 0;
}

// 轮询字段读取侧兜底: 缺失字段不崩; updated/failed 缺失时回退 okCount/errorCount
export function normalizeRefreshJob(raw: unknown): RefreshJobView {
  const job = isRecord(raw) ? raw : {};
  const result = isRecord(job.result)
    ? {
        outcome: typeof job.result.outcome === 'string' ? job.result.outcome : 'unknown',
        published: job.result.published === true,
        warnings: Array.isArray(job.result.warnings)
          ? job.result.warnings.filter((w): w is string => typeof w === 'string')
          : [],
      }
    : null;
  return {
    running: job.running === true,
    phase: typeof job.phase === 'string' ? job.phase : 'idle',
    mode: job.mode === 'all' || job.mode === 'missing' ? job.mode : null,
    total: countValue(job.total),
    processed: countValue(job.processed),
    updated: countValue(job.updated ?? job.okCount),
    noData: countValue(job.noData),
    failed: countValue(job.failed ?? job.errorCount),
    skipped: countValue(job.skipped),
    retained: countValue(job.retained),
    startedAt: stringValue(job.startedAt),
    finishedAt: stringValue(job.finishedAt),
    error: stringValue(job.error),
    result,
  };
}

// GET data 里附带的 eligible/missing; 数值才采信, 缺失保持 null (N 未加载时不禁用)
export function normalizeRefreshCounts(raw: unknown): { eligible: number | null; missing: number | null } {
  const job = isRecord(raw) ? raw : {};
  const eligible = finiteNumber(job.eligible);
  const missing = finiteNumber(job.missing);
  return { eligible, missing };
}

// POST /api/map/refresh 200 的 data 只有 {total, mode, backupFile}, 不是 job 快照;
// 但 200 即任务已启动(服务端先置 running 再返回): 这里补上 running/phase,
// 让控件立即进入进度态并触发 3s 轮询, 首次 GET 用真实进度覆盖。
// 陷阱(2026-11-05 实测回归): 直接把 POST data 喂 normalizeRefreshJob 会得到
// running=false/phase=idle —— loading 不出现、轮询守卫不通过, 页面毫无反应。
export function refreshJobFromStartPayload(raw: unknown): RefreshJobView {
  const data = isRecord(raw) ? raw : {};
  return normalizeRefreshJob({
    ...data,
    running: data.running === undefined ? true : data.running === true,
    phase: typeof data.phase === 'string' ? data.phase : 'fetching',
  });
}

// ---------------------------------------------------------------------------
// 终态统计展示 (R3)
// ---------------------------------------------------------------------------

// 终态四类统计 + 跳过/保留; 零值不展示 (沿用 collection-tasks 的 filterNonZero 约定)
export function refreshSummaryMetrics(job: RefreshJobView): { label: string; value: number }[] {
  return [
    { label: '有效更新', value: job.updated },
    { label: '无数据', value: job.noData },
    { label: '失败', value: job.failed },
    { label: '跳过', value: job.skipped },
    { label: '保留旧价', value: job.retained },
  ].filter(metric => metric.value > 0);
}

// 轮级终态文案; phase 对外枚举见 backend refresh.py
export function refreshPhaseText(job: RefreshJobView): string | null {
  if (job.running) {
    const action = job.mode === 'missing' ? '补齐中' : '刷新中';
    return `${action} ${job.processed}/${job.total}…`;
  }
  if (job.phase === 'done') {
    const outcome = job.result?.outcome;
    const labels: Record<string, string> = {
      succeeded: '全部成功', partial: '部分成功', failed: '全部失败',
      no_data: '无可用数据', skipped: '全部跳过',
    };
    const summary = refreshSummaryMetrics(job).map(m => `${m.label} ${m.value}`).join(' · ');
    const head = outcome != null && labels[outcome] ? `${labels[outcome]}：` : '已更新：';
    return summary ? `${head}${summary}` : head.replace('：', '');
  }
  if (job.phase === 'cancelled') return '已停止（数据未改动）';
  if (job.phase === 'error') return '刷新失败';
  return null;
}
