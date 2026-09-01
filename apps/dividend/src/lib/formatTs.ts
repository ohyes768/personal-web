/**
 * ISO 时间 → 固定北京时间展示。
 *
 * 带 Z / ±偏移的按绝对时刻转北京；无偏移的旧历史按 UTC 解释
 * （NAS 容器曾用 naive UTC 落盘，07:30 实际是北京 15:30）。
 */
const BEIJING = 'Asia/Shanghai';

function hasExplicitOffset(iso: string): boolean {
  return /Z$/i.test(iso) || /[+-]\d{2}:\d{2}$/.test(iso);
}

function toBeijingDate(iso: string): Date | null {
  const normalized = hasExplicitOffset(iso) ? iso : `${iso}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** ISO → "YYYY-MM-DD HH:mm"；无效或空返回 null */
export function formatBeijingTs(iso?: string | null): string | null {
  if (!iso) return null;
  const d = toBeijingDate(iso);
  if (!d) return null;
  const s = d.toLocaleString('sv-SE', { timeZone: BEIJING });
  return s.slice(0, 16);
}

/** ISO → "MM-DD HH:mm"（挡位监控卡片）；无效或空返回 null */
export function formatBeijingMdHm(iso?: string | null): string | null {
  const full = formatBeijingTs(iso);
  return full ? full.slice(5) : null;
}
