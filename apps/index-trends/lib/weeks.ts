/** 周口径日期工具。
 *
 * 周主键 = 周一（YYYY-MM-DD）；自然周区间为周一至周日。
 * 行情的 date 是该周实际最后交易日，不能拿周区间末日当成交日。
 * 全部按 UTC 解析，避免本地时区把周一挪到周日。
 */

const MS_PER_DAY = 86_400_000;

function parseDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) {
    return null;
  }
  return dt;
}

export function toIsoDate(d: Date): string {
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${mo}-${day}`;
}

export function addDays(iso: string, days: number): string {
  const d = parseDate(iso);
  if (!d) return iso;
  return toIsoDate(new Date(d.getTime() + days * MS_PER_DAY));
}

/** 自然周的周日（week_start + 6 天）。 */
export function weekEnd(weekStart: string): string {
  return addDays(weekStart, 6);
}

/** 周区间文案，如 "2026-10-26 ~ 2026-11-01"。 */
export function weekRangeLabel(weekStart: string): string {
  return `${weekStart} ~ ${weekEnd(weekStart)}`;
}

/** ISO 周编号，如 "2026-W44"。跨年周按 ISO 规则归属（周一所在年）。 */
export function isoWeekLabel(weekStart: string): string {
  const d = parseDate(weekStart);
  if (!d) return weekStart;
  const target = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNr = (target.getUTCDay() + 6) % 7; // 周一 = 0
  target.setUTCDate(target.getUTCDate() - dayNr + 3); // 该周的周四
  const isoYear = target.getUTCFullYear();
  const firstThursday = new Date(Date.UTC(isoYear, 0, 4));
  const firstDayNr = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNr + 3);
  const week = 1 + Math.round((target.getTime() - firstThursday.getTime()) / (7 * MS_PER_DAY));
  return `${isoYear}-W${String(week).padStart(2, "0")}`;
}

/** 周所属年份，用于 x 轴稀疏标签。 */
export function weekYear(weekStart: string): string {
  const d = parseDate(weekStart);
  return d ? String(d.getUTCFullYear()) : weekStart.slice(0, 4);
}

/** 在自然周分类序列里定位某个日期所属的周下标；找不到返回 -1。
 * 边界既可能是某周的周一，也可能是该周的周日，日期比较用 ISO 字符串序。
 */
export function findWeekIndex(weeks: string[], date: string): number {
  const exact = weeks.indexOf(date);
  if (exact >= 0) return exact;
  for (let i = weeks.length - 1; i >= 0; i -= 1) {
    const w = weeks[i];
    if (w <= date && weekEnd(w) >= date) return i;
  }
  return -1;
}

/** 没有 K 线的周该怎么说。
 *
 * 未来延伸由后端 extend_note 决定，不能把延伸周说成休市。
 * 拟合区内没有 K 线的槽位才是整周休市。
 */
export function emptyWeekNote(
  week: string,
  fitBoundary: string,
  futureExtension: boolean,
): string {
  if (futureExtension && week > fitBoundary) {
    return "趋势延伸，尚无K线（不是目标价）";
  }
  return "整周休市，无K线";
}

/** 周所属月份（MM），用于判断是否是 1 月的稀疏标签。 */
export function weekMonth(weekStart: string): string {
  const d = parseDate(weekStart);
  return d ? String(d.getUTCMonth() + 1).padStart(2, "0") : weekStart.slice(5, 7);
}
