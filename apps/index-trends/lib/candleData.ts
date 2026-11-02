/** 周K 数据装配（周口径）。
 *
 * x 轴是「所有自然周周一」的时间坐标：整周休市保留时间槽但没有 K 线，
 * 未来延伸周同样占位。K 线数据必须用 "-" 占位而不是 null，
 * 否则 ECharts candlestick 的 getInitialData 会抛错、整图崩溃。
 */
import type { ChartBar, ChannelSeries } from "./types";

/** ECharts candlestick 在 category 轴上的一项：[open, close, lowest, highest]。
 * 不要把周序号放在第一位，否则序号会被当成开盘价，实体从 0 画到真实价格。
 * 没有 K 线的周（整周休市、未来延伸周）用 "-"，不能用 null。
 */
export function toCandleDatum(
  bar: Pick<ChartBar, "open" | "close" | "low" | "high"> | undefined,
): [number, number, number, number] | "-" {
  if (!bar) return "-";
  return [bar.open, bar.close, bar.low, bar.high];
}

export interface ChartAxis {
  /** x 轴分类：所有自然周周一（含休市时间槽与未来延伸周）。 */
  categories: string[];
  /** 与 categories 等长的 K 线数据；无行情的周为 "-"。 */
  candleData: Array<[number, number, number, number] | "-">;
  /** week_start → 分类下标。 */
  indexByWeek: Map<string, number>;
  /** week_start → K 线。 */
  barByWeek: Map<string, ChartBar>;
}

/** 装配 x 轴分类与 K 线序列。
 *
 * 延伸段首点通常与拟合末周重复，去重后只保留一次分类；
 * 延伸段里出现拟合段没有的周时保留自己的分类（宁可留空槽也不丢值）。
 */
export function buildChartAxis(
  fit: ChannelSeries,
  ext: ChannelSeries | null,
  bars: ChartBar[],
): ChartAxis {
  const fitWeeks = new Set(fit.weeks);
  const extWeeks = ext ? ext.weeks.filter((w) => !fitWeeks.has(w)) : [];
  const categories = [...fit.weeks, ...extWeeks];

  const indexByWeek = new Map<string, number>();
  categories.forEach((w, i) => {
    if (!indexByWeek.has(w)) indexByWeek.set(w, i);
  });

  const barByWeek = new Map<string, ChartBar>();
  bars.forEach((b) => barByWeek.set(b.week_start, b));

  const candleData = categories.map((w) => toCandleDatum(barByWeek.get(w)));

  return { categories, candleData, indexByWeek, barByWeek };
}

/** 把某段通道序列摊到整条 x 轴上；没有对应分类的周留 null（断线，不跨缺口相连）。 */
export function channelValues(
  weeks: string[],
  values: number[],
  indexByWeek: Map<string, number>,
  categoryCount: number,
): Array<number | null> {
  const arr: Array<number | null> = new Array(categoryCount).fill(null);
  weeks.forEach((w, i) => {
    const idx = indexByWeek.get(w);
    if (idx !== undefined && i < values.length) arr[idx] = values[i];
  });
  return arr;
}
