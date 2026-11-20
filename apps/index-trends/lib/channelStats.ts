/** 通道位置的时间统计：在某个位置线以下停留了多久、最长连续多久。
 *
 * 位置口径与后端 `position_pct` 一致：(close − lower) ÷ (upper − lower) × 100，
 * 下轨为 0、上轨为 100，50 即中线。只统计「既有收盘价、又有轨道值」的周；
 * 整周休市的时间槽没有价格，不参与统计，也不把两侧的段落断开——
 * 它本来就连续处在低位，只是那一周没有可观察的收盘。
 */
import type { ChartBar, ChannelSeries } from "./types";

/** 页面固定展示的三条线（也是阅读分层，不是买卖阈值）。 */
export const OCCUPANCY_THRESHOLDS = [50, 40, 30] as const;

export interface OccupancyRun {
  /** 连续段的起始周（周一）。 */
  start: string;
  /** 连续段的结束周（周一）。 */
  end: string;
  weeks: number;
}

export interface OccupancyStat {
  threshold: number;
  belowWeeks: number;
  totalWeeks: number;
  /** 0—1，线下周数占统计周数的比例。 */
  share: number;
  /** 最长连续段；从未在线下时为 null。 */
  longest: OccupancyRun | null;
  /** 最新一周在线下时，它所在的连续段；否则为 null。 */
  current: OccupancyRun | null;
}

export interface ChannelOccupancy {
  /** 参与统计的周数。 */
  weeks: number;
  spanStart: string | null;
  spanEnd: string | null;
  /** 最新一周的通道位置；没有可比数据时为 null。 */
  latestPosition: number | null;
  stats: OccupancyStat[];
}

export interface WeeklyPosition {
  week: string;
  pct: number;
}

/** week_start → 上下轨。延伸区覆盖拟合区（拟合末周在两段里都有）。 */
function channelByWeek(
  fit: ChannelSeries,
  ext: ChannelSeries | null,
): Map<string, { upper: number; lower: number }> {
  const map = new Map<string, { upper: number; lower: number }>();
  const put = (series: ChannelSeries | null): void => {
    if (!series) return;
    series.weeks.forEach((week, i) => {
      const upper = series.upper[i];
      const lower = series.lower[i];
      // 宽度为 0 或缺失时不构成有效的 0—100 坐标系
      if (typeof upper !== "number" || typeof lower !== "number") return;
      if (!(upper > lower)) return;
      map.set(week, { upper, lower });
    });
  };
  put(fit);
  put(ext);
  return map;
}

/** 逐周算通道位置，只保留同时有收盘价和轨道值的周，按时间升序。 */
export function weeklyPositions(
  bars: ChartBar[],
  fit: ChannelSeries,
  ext: ChannelSeries | null,
): WeeklyPosition[] {
  const channel = channelByWeek(fit, ext);
  return [...bars]
    .sort((a, b) => (a.week_start < b.week_start ? -1 : a.week_start > b.week_start ? 1 : 0))
    .flatMap((bar) => {
      const track = channel.get(bar.week_start);
      if (!track || typeof bar.close !== "number") return [];
      const pct = ((bar.close - track.lower) / (track.upper - track.lower)) * 100;
      if (!Number.isFinite(pct)) return [];
      return [{ week: bar.week_start, pct }];
    });
}

/** 线下的所有连续段，按时间先后。图上分段着色也用它。 */
export function runsBelow(
  positions: WeeklyPosition[],
  threshold: number,
): OccupancyRun[] {
  const runs: OccupancyRun[] = [];
  let runStart = -1;

  for (let i = 0; i < positions.length; i += 1) {
    const below = positions[i].pct < threshold;
    if (below && runStart < 0) runStart = i;
    if (runStart >= 0 && (!below || i === positions.length - 1)) {
      const end = below ? i : i - 1;
      runs.push({
        start: positions[runStart].week,
        end: positions[end].week,
        weeks: end - runStart + 1,
      });
      runStart = -1;
    }
  }
  return runs;
}

/** 单条线的统计：线下周数、占比、最长连续段、当前段。 */
export function occupancyOf(
  positions: WeeklyPosition[],
  threshold: number,
): OccupancyStat {
  const runs = runsBelow(positions, threshold);
  const last = positions[positions.length - 1];

  const longest = runs.reduce<OccupancyRun | null>(
    (best, run) => (!best || run.weeks > best.weeks ? run : best),
    null,
  );
  const belowWeeks = positions.filter((item) => item.pct < threshold).length;

  return {
    threshold,
    belowWeeks,
    totalWeeks: positions.length,
    share: positions.length > 0 ? belowWeeks / positions.length : 0,
    longest,
    current: runs.length > 0 && runs[runs.length - 1].end === last?.week ? runs[runs.length - 1] : null,
  };
}

/** 通道内某个位置对应的价格：下轨 0、上轨 100 的线性插值。
 * 图上画 40%/30% 参考线用——它们在价格空间里是与轨道平行的直线。
 */
export function priceAtPosition(lower: number, upper: number, position: number): number {
  return lower + ((upper - lower) * position) / 100;
}

/** 一次算齐页面展示的三条线，外加统计区间与最新位置。 */
export function channelOccupancy(
  bars: ChartBar[],
  fit: ChannelSeries,
  ext: ChannelSeries | null,
  thresholds: readonly number[] = OCCUPANCY_THRESHOLDS,
): ChannelOccupancy {
  const positions = weeklyPositions(bars, fit, ext);
  const first = positions[0];
  const last = positions[positions.length - 1];
  return {
    weeks: positions.length,
    spanStart: first?.week ?? null,
    spanEnd: last?.week ?? null,
    latestPosition: last?.pct ?? null,
    stats: positions.length > 0 ? thresholds.map((t) => occupancyOf(positions, t)) : [],
  };
}
