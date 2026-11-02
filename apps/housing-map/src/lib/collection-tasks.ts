// 采集任务弹框的纯展示逻辑：状态徽标、指标零值过滤、相对时间。
// 全部无副作用、可被 node:test 直接覆盖（tests/collection-tasks.test.cjs）。

export type BadgeTone = 'idle' | 'running' | 'ok' | 'warn' | 'failed';

export type Metric = { label: string; value: number | string | null | undefined; unit?: string };

/** phase → 徽标文案与色调。未列出的 phase 落到 idle 并保留原串，不吞掉后端新增状态。 */
const PHASE_BADGES: Record<string, { tone: BadgeTone; label: string }> = {
  idle: { tone: 'idle', label: '尚未采集' },
  running: { tone: 'running', label: '运行中' },
  crawling: { tone: 'running', label: '运行中' },
  publishing: { tone: 'running', label: '运行中' },
  checking_sources: { tone: 'running', label: '运行中' },
  cancelling: { tone: 'running', label: '运行中' },
  succeeded: { tone: 'ok', label: '已完成' },
  done: { tone: 'ok', label: '已完成' },
  partial_failed: { tone: 'warn', label: '部分完成' },
  cooling_down: { tone: 'warn', label: '部分完成' },
  budget_exhausted: { tone: 'warn', label: '部分完成' },
  failed: { tone: 'failed', label: '失败' },
  error: { tone: 'failed', label: '失败' },
  cancelled: { tone: 'idle', label: '已取消' },
  interrupted: { tone: 'idle', label: '已中断' },
};

/** 状态徽标。`idleLabel` 只覆盖 idle 文案（租金匹配说「尚未匹配」）。 */
export function taskBadge(phase: string | undefined | null, opts: { idleLabel?: string } = {}): { tone: BadgeTone; label: string } {
  const key = phase || 'idle';
  const found = PHASE_BADGES[key];
  if (!found) return { tone: 'idle', label: key };
  if (key === 'idle' && opts.idleLabel) return { tone: found.tone, label: opts.idleLabel };
  return found;
}

/** 零值过滤：0 / undefined / null / 空串一律剔除，其余保持原顺序。 */
export function filterNonZero(metrics: Metric[]): Metric[] {
  return metrics.filter(metric => {
    if (metric.value == null) return false;
    if (typeof metric.value === 'number') return metric.value !== 0;
    const text = metric.value.trim();
    return text !== '' && text !== '0';
  });
}

/**
 * 指标渲染：非零项拼成「名 值 · 名 值」，全零返回空串。
 * `unit` 原样接在值后面（调用方决定是否带前导空格）。
 */
export function formatMetrics(metrics: Metric[]): string {
  return filterNonZero(metrics)
    .map(metric => `${metric.label} ${metric.value}${metric.unit ?? ''}`)
    .join(' · ');
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / N 周前 / N 个月前 / N 年前。
 * 口径：1~6 天用天，7~29 天用周，30~364 天用月，365 天以上用年。
 * 非法输入返回 null，让调用方决定不显示还是显示兜底文案。
 */
export function relativeTime(iso: string | undefined | null, now: number = Date.now()): string | null {
  if (!iso) return null;
  const parsed = new Date(iso).getTime();
  if (Number.isNaN(parsed)) return null;
  const elapsed = now - parsed;
  if (elapsed < 0) return '刚刚';
  if (elapsed < MINUTE) return '刚刚';
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)} 分钟前`;
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)} 小时前`;
  const days = Math.floor(elapsed / DAY);
  if (days < 7) return `${days} 天前`;
  if (days < 30) return `${Math.floor(days / 7)} 周前`;
  if (days < 365) return `${Math.floor(days / 30)} 个月前`;
  return `${Math.floor(days / 365)} 年前`;
}

/** 绝对时刻（北京时间），供相对时间的悬浮提示补口径。 */
export function absoluteTime(iso: string | undefined | null): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
}
