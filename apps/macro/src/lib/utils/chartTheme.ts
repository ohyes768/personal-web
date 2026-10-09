/** Library-independent descriptions shared by every macro time-series chart. */
export type AxisKey = 'y' | 'y2' | 'y3' | 'y4' | 'y5' | 'y6';
export type XAxisKey = 'x' | 'x2' | 'x3';
export type DateRange = [string, string] | null;
export interface AxisSpec {
  key: AxisKey; title: string; titleColor?: string; axisColor: string;
  side?: 'left' | 'right'; overlaying?: AxisKey; position?: number;
  showgrid?: boolean; zeroline?: boolean; zerolinecolor?: string;
  zerolinewidth?: number; range?: [number, number];
}
export type SubplotYAxisSpec = AxisSpec;
export interface ChartSeries {
  id: string; name: string; dates: string[]; values: (number | null)[];
  axis: AxisKey; color: string; dash: 'solid' | 'dash' | 'dot' | 'dashdot';
  width: number; unit: string; decimals: number; markers: boolean;
  details?: { label: string; values: (number | null)[]; unit?: string; decimals?: number }[];
  transform: 'raw' | 'relative' | 'normalize' | 'minMax' | 'correlation' | 'scaled';
  scaleFactor?: number;
}
export interface ChartLayout { axes: AxisSpec[]; title?: string; compact?: boolean; }
export interface SubplotSpec { xAxisKey: XAxisKey; yAxes: AxisSpec[]; title?: string; }
export interface SubplotPanelSpec {
  id?: string; traces: ChartSeries[]; spec: SubplotSpec; height?: number; emptyMessage?: string;
}
export interface ChartContext {
  chartId: string;
  series: { id: string; label: string; unit: string; transform: ChartSeries['transform']; scaleFactor?: number }[];
  dateRange: DateRange;
}
export interface LineTraceMeta {
  id: string; label: string; color: string; unit?: string; yaxis?: AxisKey;
  xaxis?: XAxisKey; dash?: ChartSeries['dash']; width?: number;
  valueFormat?: string; transform?: ChartSeries['transform']; scaleFactor?: number;
}
export function chartHeightForSubplots(count: number, compact = false): number {
  return Math.max(320, (compact ? 40 : 60) + (compact ? 220 : 260) * Math.max(1, count));
}
export function hasValidPoints(values: Array<number | null | undefined> | undefined): boolean {
  return !!values?.some((v) => v != null && Number.isFinite(v));
}
export function lastValidDate(series: ChartSeries[]): string | null {
  let last: string | null = null;
  for (const line of series) {
    for (let i = line.values.length - 1; i >= 0; i--) {
      if (line.values[i] == null) continue;
      const date = line.dates[i];
      if (date && (!last || date > last)) last = date;
      break;
    }
  }
  return last;
}
export function buildLineTrace(
  meta: LineTraceMeta, dates: string[], values: Array<number | null | undefined>,
  extras?: { details?: ChartSeries['details'] },
): ChartSeries | null {
  if (!hasValidPoints(values)) return null;
  return {
    id: meta.id, name: meta.label, dates: [...dates],
    values: dates.map((_, i) => values[i] != null && Number.isFinite(values[i]) ? values[i]! : null),
    axis: meta.yaxis ?? 'y', color: meta.color, dash: meta.dash ?? 'solid',
    width: meta.width ?? 2.5, unit: meta.unit ?? '',
    decimals: Number(meta.valueFormat?.match(/\.(\d+)f/)?.[1] ?? 2),
    markers: values.filter((v) => v != null && Number.isFinite(v)).length < 8,
    transform: meta.transform ?? 'raw', ...(meta.scaleFactor ? { scaleFactor: meta.scaleFactor } : {}), ...(extras?.details ? { details: extras.details } : {}),
  };
}
export function buildMultiAxisLayout(opts: {
  axes: AxisSpec[]; legendX?: number; margin?: { l?: number; r?: number; t?: number; b?: number };
  legendOrientation?: 'h' | 'v';
}): ChartLayout { return { axes: opts.axes }; }
export function buildSubplotLayout(opts: { spec: SubplotSpec; compact?: boolean }): ChartLayout {
  return { axes: opts.spec.yAxes, title: opts.spec.title, compact: opts.compact };
}
