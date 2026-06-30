/**
 * Plotly 暗黑主题 + 通用 layout / config — 共享给 CommodityChart / RatesChart /
 * StockIndexChart / LiquidityChart / ComparisonChart 这 5 个"多轴叠加折线"图表。
 *
 * 不动 EconomicChart / BondChart（继续走 chartConfig.ts）。
 *
 * 设计原则：
 * - 暗黑配色写死（这 5 个 Tab 都在黑底页面）
 * - axes 数组声明每个 y 轴的元信息，函数自动生成 layout.yaxis/yaxis2/...
 * - 不带任何业务元数据（label/color 由调用方提供）
 * - 不引入 spikedistance / hoverdistance（旧 chartConfig.ts 有，但 5 个新派没用到）
 */

import type { Layout, Config } from 'plotly.js';

/** 暗黑主题常量 */
export const PLOTLY_DARK = {
  paper_bgcolor: '#1a1a1a',
  plot_bgcolor: '#1a1a1a',
  fontColor: '#e5e7eb',
  gridColor: '#333',
} as const;

/** 浅色主题常量（暂未使用，预留给以后扩展） */
export const PLOTLY_LIGHT = {
  paper_bgcolor: 'white',
  plot_bgcolor: 'white',
  fontColor: '#374151',
  gridColor: '#e5e7eb',
} as const;

/**
 * 5 个新派图表共享的 Plot config —— 同样的 6 项 modeBarButtonsToRemove +
 * displaylogo + scrollZoom + doubleClick 行为。
 */
export const BASE_PLOT_CONFIG: Partial<Config> = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: [
    'lasso2d',
    'select2d',
    'hoverClosestCartesian',
    'hoverCompareCartesian',
    'zoom2d',
    'pan2d',
  ],
  scrollZoom: false,
  doubleClick: 'reset',
};

/** Plotly y 轴 key（最多支持 5 个 y 轴，已覆盖所有现有 Tab） */
export type AxisKey = 'y' | 'y2' | 'y3' | 'y4' | 'y5';

export interface AxisSpec {
  /** Plotly axis key，axes[0] 必须是 'y'（主轴） */
  key: AxisKey;
  /** 轴标题文本 */
  title: string;
  /** 轴标题字体颜色（不传则不设，沿用 layout font.color） */
  titleColor?: string;
  /** 刻度文字颜色 */
  axisColor: string;
  side: 'left' | 'right';
  /** 次轴必填 'y' */
  overlaying?: 'y';
  /** 次轴位置（0-1，越靠边越小） */
  position?: number;
  /** 是否显示 grid（默认：主轴 true，其余 false） */
  showgrid?: boolean;
  zeroline?: boolean;
  zerolinecolor?: string;
  zerolinewidth?: number;
}

export interface MultiAxisLayoutOpts {
  axes: AxisSpec[];
  /** legend x 位置（默认 1.02） */
  legendX?: number;
  /** margin（默认 l:80, r:200, t:40, b:60） */
  margin?: { l?: number; r?: number; t?: number; b?: number };
}

const DEFAULT_MARGIN = { l: 80, r: 200, t: 40, b: 60 } as const;

/**
 * 生成"多轴叠加折线图"的标准 layout：
 * - xaxis 用 PLOTLY_DARK 主题
 * - axes[0] 默认 y 主轴（showgrid 自动 true）
 * - 其他 axes 默认 showgrid:false
 * - 应用 PLOTLY_DARK 配色 + hovermode: 'x unified' + 右侧外置 legend
 */
export function buildMultiAxisLayout(opts: MultiAxisLayoutOpts): Partial<Layout> {
  const { axes, legendX = 1.02, margin = {} } = opts;
  const finalMargin = { ...DEFAULT_MARGIN, ...margin };

  const xaxis = {
    title: '日期',
    showgrid: true,
    gridcolor: PLOTLY_DARK.gridColor,
    color: PLOTLY_DARK.fontColor,
  };

  const yAxes: Record<string, unknown> = {};
  axes.forEach((axis, idx) => {
    const isMain = idx === 0;
    const showgrid = axis.showgrid ?? isMain;
    const titleObj = axis.titleColor
      ? { text: axis.title, font: { color: axis.titleColor } }
      : axis.title;
    const yAxisDef: Record<string, unknown> = {
      title: titleObj,
      side: axis.side,
      overlaying: axis.overlaying,
      position: axis.position,
      showgrid,
      gridcolor: PLOTLY_DARK.gridColor,
      color: axis.axisColor,
    };
    if (axis.zeroline !== undefined) {
      yAxisDef.zeroline = axis.zeroline;
      yAxisDef.zerolinecolor = axis.zerolinecolor;
      yAxisDef.zerolinewidth = axis.zerolinewidth;
    }
    yAxes[axis.key] = yAxisDef;
  });

  return {
    xaxis,
    ...yAxes,
    hovermode: 'x unified',
    paper_bgcolor: PLOTLY_DARK.paper_bgcolor,
    plot_bgcolor: PLOTLY_DARK.plot_bgcolor,
    font: { color: PLOTLY_DARK.fontColor },
    showlegend: true,
    legend: {
      orientation: 'v',
      y: 0.5,
      x: legendX,
      xanchor: 'left',
      yanchor: 'middle',
    },
    margin: finalMargin,
  } as Partial<Layout>;
}