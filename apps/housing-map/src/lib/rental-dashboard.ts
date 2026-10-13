// 数据看板租金三列的排序、索引与展示纯函数。
// 全部无副作用、可被 node:test 直接覆盖（tests/rental-dashboard.test.cjs）。
import type { RentalRefreshJob, RentalSummaryEntry } from './rental-types';

/** 看板租金三列对应的排序键（并入看板 DashSortKey 使用） */
export type RentalSortKey = 'rent_unit' | 'rent_yield' | 'rent_samples';

/**
 * 排序取值：缺失（小区无摘要 / 数值为 null）一律返回 null，比较时永远沉底。
 * 样本数为 0 不算有效排序依据，同样按缺失处理。
 */
export function rentalSortValue(
  summary: RentalSummaryEntry | undefined,
  key: RentalSortKey,
): number | null {
  if (!summary) return null;
  switch (key) {
    case 'rent_unit':
      return summary.unit_rent_yuan_m2_month;
    case 'rent_yield':
      return summary.annualized_gross_yield_pct;
    case 'rent_samples':
      return summary.sample_count > 0 ? summary.sample_count : null;
  }
}

/** 数值比较：缺失（null）无论升降序永远排在末尾 */
export function compareNumericMissingLast(
  a: number | null,
  b: number | null,
  order: 'asc' | 'desc',
): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return order === 'desc' ? b - a : a - b;
}

/** 不可变排序：返回新数组，不修改入参 */
export function sortRowsByRentalKey<T>(
  rows: readonly T[],
  valueOf: (row: T) => number | null,
  order: 'asc' | 'desc',
): T[] {
  return [...rows].sort((a, b) => compareNumericMissingLast(valueOf(a), valueOf(b), order));
}

export function isRentalSortKey(key: string): boolean {
  return key === 'rent_unit' || key === 'rent_yield' || key === 'rent_samples';
}

/** 按 community_id 建索引，重复 id 后者覆盖（后端保证唯一，此处仅为容错） */
export function indexSummaries(
  summaries: readonly RentalSummaryEntry[],
): Record<string, RentalSummaryEntry> {
  return Object.fromEntries(summaries.map(entry => [entry.community_id, entry]));
}

// ---- 三列单元格显示值：缺失一律 '—' ----

export function formatUnitRentCell(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(1);
}

export function formatYieldCell(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(2)}%`;
}

export function formatSampleCountCell(value: number | undefined): string {
  return value == null ? '—' : String(value);
}

// ---- 刷新任务文案（看板与详情共用，不假装百分比）----

/** 运行中进度文案；非运行态返回 null */
export function rentalRefreshProgressText(job: RentalRefreshJob | null): string | null {
  if (!job) return null;
  if (job.phase === 'cancelling') return '正在取消…';
  if (job.stage === 'checking') return '正在检查租金来源…';
  if (job.stage === 'discovering' && job.association) return `正在查找来源 ${job.association.checked}/${job.association.targets} 小区`;
  if (job.stage === 'publishing') return '正在保存租金数据…';
  if (job.total_communities > 0) {
    return `已处理 ${job.processed_communities}/${job.total_communities} 小区`;
  }
  return '正在准备租金更新…';
}

/** 终态结果文案；运行中或无任务返回 null */
export function rentalRefreshTerminalNote(job: RentalRefreshJob | null): string | null {
  if (!job) return null;
  // 取消/中断从不发布，优先于 result 计数（后端取消任务仍带 result，不能显示成"成功 X/失败 Y"）
  if (job.phase === 'cancelled') return '上次更新已取消，数据未改动';
  if (job.phase === 'interrupted') return '上次更新被中断，数据未改动';
  if (job.result) {
    const a = job.association;
    return `上次更新：成功 ${job.result.success_count} / 失败 ${job.result.failed_count}` + (a ?
      ` · 待选择 ${a.pending} · 暂无来源 ${a.missing} · 查找失败 ${a.failed} · 已跳过 ${a.skipped} · 排除 ${a.excluded}` : '');
  }
  if (job.phase === 'failed') return '上次更新失败，数据未改动';
  return null;
}
