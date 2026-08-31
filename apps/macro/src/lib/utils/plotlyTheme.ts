/**
 * Plotly 暗黑主题 + 可组合 layout / trace builders
 *
 * 共享给宏观页各时序图：
 * - 主题、config、图例、边距、spike
 * - 时间轴 / 数值轴 / 联动子图 domain
 * - 折线 trace 工厂与空序列过滤
 *
 * 不包含业务指标元数据（label/color/unit 由调用方提供）。
 */

import type { Layout, Config, Data } from 'plotly.js';

/** 暗黑主题常量 */
export const PLOTLY_DARK = {
  paper_bgcolor: '#1a1a1a',
  plot_bgcolor: '#1a1a1a',
  fontColor: '#e5e7eb',
  gridColor: '#2a2a2a',
  axisLineColor: '#4b5563',
  hoverBg: '#111827',
  hoverBorder: '#6b7280',
} as const;

/** 浅色主题常量（预留） */
export const PLOTLY_LIGHT = {
  paper_bgcolor: 'white',
  plot_bgcolor: 'white',
  fontColor: '#374151',
  gridColor: '#e5e7eb',
  axisLineColor: '#d1d5db',
  hoverBg: '#ffffff',
  hoverBorder: '#9ca3af',
} as const;

/** 共享 Plot config：保留缩放/复位，去掉套索选择 */
export const BASE_PLOT_CONFIG: Partial<Config> = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: [
    'lasso2d',
    'select2d',
    'hoverClosestCartesian',
    'hoverCompareCartesian',
  ],
  scrollZoom: false,
  doubleClick: 'reset',
};

/** Plotly y 轴 key（最多 6 轴，覆盖 3 子图 × 双轴） */
export type AxisKey = 'y' | 'y2' | 'y3' | 'y4' | 'y5' | 'y6';
export type XAxisKey = 'x' | 'x2' | 'x3';

export interface AxisSpec {
  key: AxisKey;
  title: string;
  titleColor?: string;
  axisColor: string;
  side: 'left' | 'right';
  overlaying?: AxisKey;
  position?: number;
  showgrid?: boolean;
  zeroline?: boolean;
  zerolinecolor?: string;
  zerolinewidth?: number;
  range?: [number, number];
}

export interface MultiAxisLayoutOpts {
  axes: AxisSpec[];
  legendX?: number;
  margin?: { l?: number; r?: number; t?: number; b?: number };
  /** 兼容旧调用；新图优先用顶部横排图例 */
  legendOrientation?: 'h' | 'v';
}

export interface LineTraceMeta {
  label: string;
  color: string;
  unit?: string;
  yaxis?: AxisKey;
  xaxis?: XAxisKey;
  dash?: 'solid' | 'dash' | 'dot' | 'dashdot';
  width?: number;
  hoverLabel?: string;
  valueFormat?: string;
}

export interface SubplotYAxisSpec {
  key: AxisKey;
  title: string;
  titleColor?: string;
  axisColor: string;
  side?: 'left' | 'right';
  /** 相对本子图主轴 overlay；主轴不设 */
  overlaying?: AxisKey;
  zeroline?: boolean;
  zerolinecolor?: string;
  zerolinewidth?: number;
  range?: [number, number];
  showgrid?: boolean;
}

export interface SubplotSpec {
  /** 本子图 x 轴：第一行 x，第二行 x2，第三行 x3 */
  xAxisKey: XAxisKey;
  yAxes: SubplotYAxisSpec[];
  /** 子图标题（可选，画在子图顶部） */
  title?: string;
}

const SHORT_SERIES_MARKER_THRESHOLD = 8;

/** Plotly 会把显式 undefined 当成非法枚举，必须在写入 layout 前剥掉 */
function omitUndefined<T extends Record<string, unknown>>(obj: T): T {
  return Object.fromEntries(
    Object.entries(obj).filter(([, value]) => value !== undefined),
  ) as T;
}

/** 布局轴字段名：y → yaxis，y2 → yaxis2 */
export function layoutAxisKey(axisKey: AxisKey | XAxisKey): string {
  if (axisKey === 'x' || axisKey === 'y') {
    return axisKey === 'x' ? 'xaxis' : 'yaxis';
  }
  if (axisKey.startsWith('x')) return `xaxis${axisKey.slice(1)}`;
  return `yaxis${axisKey.slice(1)}`;
}

/** 子图纵向 domain，从上到下；gap 为子图间距 */
export function buildSubplotDomains(
  count: 1 | 2 | 3,
  gap = 0.07,
): Array<[number, number]> {
  if (count === 1) return [[0, 1]];
  if (count === 2) {
    const mid = 0.5 + gap / 2;
    return [
      [mid, 1],
      [0, 0.5 - gap / 2],
    ];
  }
  const band = (1 - gap * 2) / 3;
  const top: [number, number] = [1 - band, 1];
  const mid: [number, number] = [band + gap, band + gap + band];
  const bottom: [number, number] = [0, band];
  return [top, mid, bottom];
}

/** 按子图数量估算图表高度 */
export function chartHeightForSubplots(count: number, compact = false): number {
  const per = compact ? 220 : 260;
  const base = compact ? 40 : 60;
  return Math.max(320, base + per * Math.max(1, count));
}

/** 序列是否有至少一个有效数值 */
export function hasValidPoints(values: Array<number | null | undefined> | undefined): boolean {
  if (!values || values.length === 0) return false;
  return values.some((v) => v != null && !Number.isNaN(v as number));
}

/** 有效点数量 */
export function countValidPoints(values: Array<number | null | undefined>): number {
  return values.filter((v) => v != null && !Number.isNaN(v as number)).length;
}

export function buildBaseLayout(opts?: {
  margin?: { l?: number; r?: number; t?: number; b?: number };
  compact?: boolean;
}): Partial<Layout> {
  const compact = opts?.compact ?? false;
  const margin = {
    l: compact ? 52 : 68,
    r: compact ? 36 : 52,
    t: compact ? 56 : 72,
    b: compact ? 44 : 52,
    ...(opts?.margin ?? {}),
  };

  return {
    autosize: true,
    paper_bgcolor: PLOTLY_DARK.paper_bgcolor,
    plot_bgcolor: PLOTLY_DARK.plot_bgcolor,
    font: {
      color: PLOTLY_DARK.fontColor,
      size: compact ? 11 : 12,
    },
    hovermode: 'x unified',
    hoverlabel: {
      bgcolor: PLOTLY_DARK.hoverBg,
      bordercolor: PLOTLY_DARK.hoverBorder,
      font: { color: PLOTLY_DARK.fontColor, size: compact ? 11 : 12 },
    },
    showlegend: true,
    legend: {
      orientation: 'h',
      y: 1.02,
      yanchor: 'bottom',
      x: 0,
      xanchor: 'left',
      bgcolor: 'rgba(0,0,0,0)',
      font: { size: compact ? 11 : 12 },
    },
    margin,
    // Plotly 运行时支持，@types/plotly.js 未声明
    ...({ spikedistance: -1, hoverdistance: 40 } as Record<string, unknown>),
  } as Partial<Layout>;
}

export function buildTimeAxis(opts: {
  isBottom: boolean;
  matches?: XAxisKey;
  compact?: boolean;
  title?: string;
}): Record<string, unknown> {
  const { isBottom, matches, compact = false, title } = opts;
  return omitUndefined({
    title: isBottom ? (title ?? '日期') : undefined,
    showgrid: true,
    gridcolor: PLOTLY_DARK.gridColor,
    color: PLOTLY_DARK.fontColor,
    // 只让底部日期轴自动撑边距；所有轴都 automargin 会把绘图区挤成 0
    automargin: isBottom,
    showspikes: true,
    spikemode: 'across',
    spikesnap: 'cursor',
    spikethickness: 1,
    spikecolor: '#6b7280',
    nticks: compact ? 4 : 8,
    matches,
  });
}

export function buildValueAxis(opts: {
  title: string;
  titleColor?: string;
  axisColor: string;
  side?: 'left' | 'right';
  overlaying?: AxisKey;
  position?: number;
  showgrid?: boolean;
  zeroline?: boolean;
  zerolinecolor?: string;
  zerolinewidth?: number;
  range?: [number, number];
  domain?: [number, number];
  anchor?: XAxisKey;
}): Record<string, unknown> {
  const titleObj = opts.titleColor
    ? { text: opts.title, font: { color: opts.titleColor, size: 12 } }
    : { text: opts.title, font: { size: 12 } };

  return omitUndefined({
    title: titleObj,
    side: opts.side ?? 'left',
    overlaying: opts.overlaying,
    position: opts.position,
    showgrid: opts.showgrid ?? true,
    gridcolor: PLOTLY_DARK.gridColor,
    color: opts.axisColor,
    // overlaying 轴再开 automargin 会和主轴抢边距，绘图区容易塌掉
    automargin: !opts.overlaying,
    zeroline: opts.zeroline ?? false,
    zerolinecolor: opts.zerolinecolor,
    zerolinewidth: opts.zerolinewidth,
    range: opts.range,
    domain: opts.domain,
    anchor: opts.anchor,
    separatethousands: true,
  });
}

/**
 * 生成上下联动子图 layout。
 * 每个 subplot 可有 1 至 2 个 Y 轴；日期轴通过 matches 联动到第一个 x。
 */
export function buildLinkedSubplotLayout(opts: {
  subplots: SubplotSpec[];
  compact?: boolean;
  margin?: { l?: number; r?: number; t?: number; b?: number };
}): Partial<Layout> {
  const { subplots, compact = false } = opts;
  const count = Math.min(3, Math.max(1, subplots.length)) as 1 | 2 | 3;
  const base = buildBaseLayout({ compact, margin: opts.margin });
  const layout: Record<string, unknown> = {
    ...base,
    // 用 grid 分摊子图高度。手动 domain + matches + 全轴 automargin
    // 会在 hidden Tab（宽高为 0）首次 newPlot 时把绘图区算成空白。
    grid: {
      rows: count,
      columns: 1,
      pattern: 'independent',
      roworder: 'top to bottom',
      ygap: compact ? 0.1 : 0.08,
    },
  };

  subplots.forEach((subplot, idx) => {
    const isBottom = idx === subplots.length - 1;
    const mainY = subplot.yAxes[0];
    if (!mainY) return;

    const xLayoutKey = layoutAxisKey(subplot.xAxisKey);
    layout[xLayoutKey] = omitUndefined({
      ...buildTimeAxis({
        isBottom,
        matches: idx === 0 ? undefined : 'x',
        compact,
      }),
      anchor: mainY.key,
    });

    subplot.yAxes.forEach((axis, axisIdx) => {
      const isMain = axisIdx === 0;
      layout[layoutAxisKey(axis.key)] = buildValueAxis({
        title: axis.title,
        titleColor: axis.titleColor,
        axisColor: axis.axisColor,
        side: axis.side ?? (isMain ? 'left' : 'right'),
        overlaying: isMain ? undefined : (axis.overlaying ?? mainY.key),
        showgrid: axis.showgrid ?? isMain,
        zeroline: axis.zeroline,
        zerolinecolor: axis.zerolinecolor,
        zerolinewidth: axis.zerolinewidth,
        range: axis.range,
        anchor: subplot.xAxisKey,
      });
    });
  });

  return layout as Partial<Layout>;
}

/**
 * 兼容旧多轴叠加图。图例改为顶部横排，并启用 automargin / spike。
 */
export function buildMultiAxisLayout(opts: MultiAxisLayoutOpts): Partial<Layout> {
  const {
    axes,
    legendOrientation = 'h',
    margin = {},
  } = opts;

  const base = buildBaseLayout({
    margin: {
      l: 68,
      r: legendOrientation === 'v' ? 160 : 52,
      t: legendOrientation === 'h' ? 72 : 48,
      b: 52,
      ...margin,
    },
  });

  const layout: Record<string, unknown> = {
    ...base,
    xaxis: {
      ...buildTimeAxis({ isBottom: true }),
    },
  };

  if (legendOrientation === 'v') {
    layout.legend = {
      orientation: 'v',
      y: 0.5,
      x: opts.legendX ?? 1.02,
      xanchor: 'left',
      yanchor: 'middle',
      bgcolor: 'rgba(0,0,0,0)',
    };
  }

  axes.forEach((axis, idx) => {
    const isMain = idx === 0;
    layout[layoutAxisKey(axis.key)] = buildValueAxis({
      title: axis.title,
      titleColor: axis.titleColor,
      axisColor: axis.axisColor,
      side: axis.side,
      overlaying: axis.overlaying,
      position: axis.position,
      showgrid: axis.showgrid ?? isMain,
      zeroline: axis.zeroline,
      zerolinecolor: axis.zerolinecolor,
      zerolinewidth: axis.zerolinewidth,
      range: axis.range,
    });
  });

  return layout as Partial<Layout>;
}

/**
 * 统一折线 trace。空序列返回 null，调用方应过滤。
 * 有效点 < 8 时自动加 marker，避免短序列“看不见”。
 */
export function buildLineTrace(
  meta: LineTraceMeta,
  x: string[],
  y: Array<number | null | undefined>,
  extras?: {
    customdata?: unknown[];
    hovertemplate?: string;
  },
): Data | null {
  if (!hasValidPoints(y)) return null;

  const validCount = countValidPoints(y);
  const showMarkers = validCount < SHORT_SERIES_MARKER_THRESHOLD;
  const unit = meta.unit ? ` ${meta.unit}` : '';
  const fmt = meta.valueFormat ?? '.2f';
  const hovertemplate =
    extras?.hovertemplate ??
    `<b>${meta.hoverLabel ?? meta.label}</b><br>` +
      `%{y:${fmt}}${unit}` +
      `<extra></extra>`;

  return {
    type: 'scatter',
    mode: showMarkers ? 'lines+markers' : 'lines',
    name: meta.label,
    x,
    y: y as (number | null)[],
    customdata: extras?.customdata,
    xaxis: meta.xaxis ?? 'x',
    yaxis: meta.yaxis ?? 'y',
    line: {
      color: meta.color,
      width: meta.width ?? 2.5,
      dash: meta.dash ?? 'solid',
    },
    marker: showMarkers
      ? { size: 6, color: meta.color }
      : undefined,
    hovertemplate,
    connectgaps: false,
  } as Data;
}
