import type { ChartBar } from "./types";

/** ECharts candlestick 在 category 轴上的一项：[open, close, lowest, highest]。
 * 不要把月份序号放在第一位，否则序号会被当成开盘价，实体从 0 画到真实价格。
 * 没有 K 线的月份用 "-"，不能用 null。
 */
export function toCandleDatum(
  bar: Pick<ChartBar, "open" | "close" | "low" | "high"> | undefined,
): [number, number, number, number] | "-" {
  if (!bar) return "-";
  return [bar.open, bar.close, bar.low, bar.high];
}
