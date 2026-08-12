/**
 * 各分组在指定月份的发布日期规则
 *
 * 规则来源:各 skill 的 SKILL.md「数据发布时间」表
 * - 货币政策: DR007 每工作日; MLF 每月15日(节假日顺延); LPR 每月20日(节假日顺延)
 * - 信用扩张: M2/M1/社融 每月12-15日窗口,取第一个工作日
 * - 经济运行: 铁路货运 7日 + 工业增加值/固投/社零 13日 + 用电量 20日
 * - 通胀环境: CPI/PPI 每月10日
 * - 外部压力: 每工作日
 * - 市场情绪: 每工作日
 *
 * 所有具体日期都做工作日校正:落在周末则前移到最近的工作日
 */
import type { DimensionKey } from './types';

/** 给定年月日,返回该日或之前最近的工作日(只在该月内查找) */
export function getWorkdayOnOrBefore(year: number, month: number, day: number): Date | null {
  const d = new Date(Date.UTC(year, month - 1, day));
  while (d.getUTCMonth() === month - 1) {
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) return d;
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return null;
}

/** 获取该月所有工作日(周一到周五) */
export function getWorkdaysInMonth(year: number, month: number): Date[] {
  const days: Date[] = [];
  const d = new Date(Date.UTC(year, month - 1, 1));
  while (d.getUTCMonth() === month - 1) {
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) days.push(new Date(d));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return days;
}

/** Date → 'YYYY-MM-DD' */
function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** 解析 'YYYY-MM' 为 [year, month] */
function parseMonth(month: string): [number, number] {
  const [y, m] = month.split('-').map(Number);
  return [y, m];
}

/** 对给定月份,返回该分组在该月的所有发布日期(YYYY-MM-DD,已做工作日校正) */
export function getReleaseDates(month: string, groupKey: DimensionKey): string[] {
  const [year, mon] = parseMonth(month);
  const dates = new Set<string>();
  const addISO = (d: Date | null) => { if (d) dates.add(toISO(d)); };
  const addAllWorkdays = () => getWorkdaysInMonth(year, mon).forEach(d => addISO(d));

  switch (groupKey) {
    case 'monetary_policy':
      // DR007 每个工作日 + MLF 15日 + LPR 20日
      addAllWorkdays();
      addISO(getWorkdayOnOrBefore(year, mon, 15));
      addISO(getWorkdayOnOrBefore(year, mon, 20));
      break;
    case 'money_supply':
      // M2/M1/社融 12-15日窗口,取该窗口第一个工作日(用 13 日近似)
      addISO(getWorkdayOnOrBefore(year, mon, 13));
      break;
    case 'entity_economy':
      // 铁路货运 7日 + 工业增加值/固投/社零 13日 + 用电量/中长期贷款 20日
      addISO(getWorkdayOnOrBefore(year, mon, 7));
      addISO(getWorkdayOnOrBefore(year, mon, 13));
      addISO(getWorkdayOnOrBefore(year, mon, 20));
      break;
    case 'inflation':
      // CPI/PPI 每月10日
      addISO(getWorkdayOnOrBefore(year, mon, 10));
      break;
    case 'exchange_rate':
    case 'risk_appetite':
      // 每个工作日
      addAllWorkdays();
      break;
  }

  return Array.from(dates).sort();
}

/** 聚合该月所有分组的发布日期 → { 'YYYY-MM-DD': DimensionKey[] } */
export function getReleaseCalendar(month: string): Record<string, DimensionKey[]> {
  const result: Record<string, DimensionKey[]> = {};
  const groupKeys: DimensionKey[] = [
    'monetary_policy', 'money_supply', 'entity_economy',
    'inflation', 'exchange_rate', 'risk_appetite',
  ];
  for (const key of groupKeys) {
    for (const iso of getReleaseDates(month, key)) {
      if (!result[iso]) result[iso] = [];
      result[iso].push(key);
    }
  }
  return result;
}
