/**
 * Plotly 图表配置工具函数
 */
import type { ChartTrace, ChartColors } from '../types/economic';

/** 图表颜色配置 */
export const CHART_COLORS: ChartColors = {
  treasury3M: '#3B82F6',  // 蓝色
  treasury2Y: '#10B981',  // 绿色
  treasury10Y: '#F59E0B', // 橙色
  euroBond10Y: '#EF4444', // 红色（欧债）
  japanBond10Y: '#8B5CF6', // 紫色（日债）
  dollarIndex: '#06B6D4', // 青色
  usdCny: '#EC4899',      // 粉色
  usdJpy: '#F59E0B',      // 橙色
  usdEur: '#10B981',      // 绿色
  vix: '#9467BD',         // 紫色（VIX恐慌指数）
};

/**
 * 生成美债图表数据系列
 */
export function createTreasuryTraces(
  dates: string[],
  data: { '3m': number[]; '2y': number[]; '10y': number[] }
): ChartTrace[] {
  return [
    {
      x: dates,
      y: data['3m'],
      name: '3个月期',
      mode: 'lines',
      line: { color: CHART_COLORS.treasury3M, width: 2 },
      xaxis: 'x',
      yaxis: 'y',
    },
    {
      x: dates,
      y: data['2y'],
      name: '2年期',
      mode: 'lines',
      line: { color: CHART_COLORS.treasury2Y, width: 2 },
      xaxis: 'x',
      yaxis: 'y',
    },
    {
      x: dates,
      y: data['10y'],
      name: '10年期',
      mode: 'lines',
      line: { color: CHART_COLORS.treasury10Y, width: 2 },
      xaxis: 'x',
      yaxis: 'y',
    },
  ];
}

/**
 * 生成欧债图表数据系列
 */
export function createEuroBondTraces(
  dates: string[],
  data: { '10y': number[] }
): ChartTrace[] {
  return [
    {
      x: dates,
      y: data['10y'],
      name: '德国 10 年期',
      mode: 'lines+markers',
      line: { color: CHART_COLORS.euroBond10Y, width: 2 },
      xaxis: 'x3',
      yaxis: 'y3',
    },
  ];
}

/**
 * 生成日债图表数据系列
 */
export function createJapanBondTraces(
  dates: string[],
  data: { '10y': number[] }
): ChartTrace[] {
  return [
    {
      x: dates,
      y: data['10y'],
      name: '日本 10 年期',
      mode: 'lines+markers',
      line: { color: CHART_COLORS.japanBond10Y, width: 2 },
      xaxis: 'x4',
      yaxis: 'y4',
    },
  ];
}

/**
 * 计算相对变化百分比
 * @param values 原始值数组
 * @returns 相对变化百分比数组
 */
function calculateRelativeChange(values: number[]): number[] {
  // 找到第一个非空值作为基准
  const baseValue = values.find(v => v !== null && v !== undefined && !isNaN(v));
  if (!baseValue) return values;

  return values.map(v => {
    if (v === null || v === undefined || isNaN(v)) return v;
    // 计算相对变化百分比
    return ((v - baseValue) / baseValue) * 100;
  });
}

/**
 * 生成汇率图表数据系列（显示相对变化百分比）
 */
export function createExchangeTraces(
  dates: string[],
  data: {
    dollar_index: number[];
    usd_cny: number[];
    usd_jpy: number[];
    usd_eur: number[];
  }
): ChartTrace[] {
  return [
    {
      x: dates,
      y: calculateRelativeChange(data.dollar_index),
      name: '美元指数',
      mode: 'lines',
      line: { color: CHART_COLORS.dollarIndex, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: calculateRelativeChange(data.usd_cny),
      name: 'USD/CNY',
      mode: 'lines',
      line: { color: CHART_COLORS.usdCny, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: calculateRelativeChange(data.usd_jpy),
      name: 'USD/JPY',
      mode: 'lines',
      line: { color: CHART_COLORS.usdJpy, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: calculateRelativeChange(data.usd_eur),
      name: 'USD/EUR',
      mode: 'lines',
      line: { color: CHART_COLORS.usdEur, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
  ];
}

/**
 * 生成VIX图表数据系列
 */
export function createVIXTraces(
  dates: string[],
  data: number[]
): ChartTrace[] {
  return [
    {
      x: dates,
      y: data,
      name: 'VIX恐慌指数',
      mode: 'lines',
      line: { color: CHART_COLORS.vix, width: 2 },
      xaxis: 'x3',
      yaxis: 'y3',
    },
  ];
}

/**
 * 生成图表布局配置
 */
export function createChartLayout(isDarkMode: boolean) {
  const bgColor = isDarkMode ? '#1a1a1a' : 'white';
  const gridColor = isDarkMode ? '#333' : '#e5e7eb';
  const textColor = isDarkMode ? '#e5e7eb' : '#374151';

  return {
    grid: {
      rows: 4,
      columns: 1,
      pattern: 'independent',
    },
    // 美债收益率图（第 1 行）
    xaxis: {
      title: '日期',
      anchor: 'y',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
    },
    yaxis: {
      title: '收益率 (%)',
      anchor: 'x',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 欧债收益率图（第 2 行）
    xaxis3: {
      title: '日期',
      anchor: 'y3',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x',
    },
    yaxis3: {
      title: '收益率 (%)',
      anchor: 'x3',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 日债收益率图（第 3 行）
    xaxis4: {
      title: '日期',
      anchor: 'y4',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x',
    },
    yaxis4: {
      title: '收益率 (%)',
      anchor: 'x4',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 汇率图（第 4 行）
    xaxis2: {
      title: '日期',
      anchor: 'y2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x',
    },
    yaxis2: {
      title: '汇率相对变化 (%)',
      anchor: 'x2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 通用配置
    hovermode: 'x unified' as const,
    spikedistance: -1,
    hoverdistance: 50,
    // 暗色模式背景
    paper_bgcolor: bgColor,
    plot_bgcolor: bgColor,
    font: {
      color: textColor,
    },
    // 图例配置
    showlegend: true,
    legend: {
      orientation: 'v' as const,
      y: 0.5,
      x: 1.02,
      xanchor: 'left' as const,
      yanchor: 'middle' as const,
    },
    // 边距
    margin: {
      l: 60,
      r: 150,
      t: 40,
      b: 60,
    },
    // 子图间距
    vertical_spacing: 0.08,
  };
}

/**
 * 生成图表配置
 */
export function createChartConfig() {
  return {
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
    // 禁用滚轮缩放
    scrollZoom: false,
    // 双击重置
    doubleClick: 'reset' as const,
  };
}

/**
 * 生成2个子图的布局配置（美债 + 汇率）
 */
export function createTwoChartLayout(isDarkMode: boolean) {
  const bgColor = isDarkMode ? '#1a1a1a' : 'white';
  const gridColor = isDarkMode ? '#333' : '#e5e7eb';
  const textColor = isDarkMode ? '#e5e7eb' : '#374151';

  return {
    grid: {
      rows: 2,
      columns: 1,
      pattern: 'independent',
    },
    // 美债收益率图（第 1 行）
    xaxis: {
      title: '日期',
      anchor: 'y',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
    },
    yaxis: {
      title: '收益率 (%)',
      anchor: 'x',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 汇率图（第 2 行）
    xaxis2: {
      title: '日期',
      anchor: 'y2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x', // X轴联动
    },
    yaxis2: {
      title: '汇率相对变化 (%)',
      anchor: 'x2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 通用配置
    hovermode: 'x unified' as const,
    spikedistance: -1,
    hoverdistance: 50,
    // 暗色模式背景
    paper_bgcolor: bgColor,
    plot_bgcolor: bgColor,
    font: {
      color: textColor,
    },
    // 图例配置
    showlegend: true,
    legend: {
      orientation: 'v' as const,
      y: 0.5,
      x: 1.02,
      xanchor: 'left' as const,
      yanchor: 'middle' as const,
    },
    // 边距
    margin: {
      l: 60,
      r: 150,
      t: 40,
      b: 60,
    },
    // 子图间距
    vertical_spacing: 0.08,
  };
}

/**
 * 生成3个子图的布局配置（美债 + 汇率 + VIX）
 */
export function createThreeChartLayout(isDarkMode: boolean) {
  const bgColor = isDarkMode ? '#1a1a1a' : 'white';
  const gridColor = isDarkMode ? '#333' : '#e5e7eb';
  const textColor = isDarkMode ? '#e5e7eb' : '#374151';

  return {
    grid: {
      rows: 3,
      columns: 1,
      pattern: 'independent',
    },
    // 美债收益率图（第 1 行）
    xaxis: {
      title: '日期',
      anchor: 'y',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
    },
    yaxis: {
      title: '收益率 (%)',
      anchor: 'x',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 汇率图（第 2 行）
    xaxis2: {
      title: '日期',
      anchor: 'y2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x', // X轴联动
    },
    yaxis2: {
      title: '汇率相对变化 (%)',
      anchor: 'x2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // VIX恐慌指数图（第 3 行）
    xaxis3: {
      title: '日期',
      anchor: 'y3',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      matches: 'x', // X轴联动
    },
    yaxis3: {
      title: 'VIX指数',
      anchor: 'x3',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 通用配置
    hovermode: 'x unified' as const,
    spikedistance: -1,
    hoverdistance: 50,
    // 暗色模式背景
    paper_bgcolor: bgColor,
    plot_bgcolor: bgColor,
    font: {
      color: textColor,
    },
    // 图例配置
    showlegend: true,
    legend: {
      orientation: 'v' as const,
      y: 0.5,
      x: 1.02,
      xanchor: 'left' as const,
      yanchor: 'middle' as const,
    },
    // 边距
    margin: {
      l: 60,
      r: 150,
      t: 40,
      b: 60,
    },
    // 子图间距
    vertical_spacing: 0.08,
  };
}

/**
 * 生成德债日债图表布局配置（1个子图，4条线）
 */
export function createBondChartLayout(isDarkMode: boolean) {
  const bgColor = isDarkMode ? '#1a1a1a' : 'white';
  const gridColor = isDarkMode ? '#333' : '#e5e7eb';
  const textColor = isDarkMode ? '#e5e7eb' : '#374151';

  return {
    // 德债日债图表（1个子图）
    xaxis: {
      title: '日期',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
    },
    yaxis: {
      title: '收益率 (%)',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
      fixedrange: true,
    },
    // 通用配置
    hovermode: 'x unified' as const,
    spikedistance: -1,
    hoverdistance: 50,
    // 暗色模式背景
    paper_bgcolor: bgColor,
    plot_bgcolor: bgColor,
    font: {
      color: textColor,
    },
    // 图例配置
    showlegend: true,
    legend: {
      orientation: 'v' as const,
      y: 0.5,
      x: 1.02,
      xanchor: 'left' as const,
      yanchor: 'middle' as const,
    },
    // 边距
    margin: {
      l: 60,
      r: 150,
      t: 40,
      b: 60,
    },
  };
}

/**
 * 生成德债日债图表配置
 */
export function createBondChartConfig() {
  return {
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
    // 禁用滚轮缩放
    scrollZoom: false,
    // 双击重置
    doubleClick: 'reset' as const,
  };
}

/**
 * 生成图表标题配置
 */
export function createChartAnnotations() {
  return [
    {
      text: '美国国债收益率',
      x: 0.5,
      y: 1.02,
      xref: 'paper',
      yref: 'paper',
      showarrow: false,
      font: { size: 16, color: '#374151' },
      xanchor: 'center' as const,
    },
    {
      text: '汇率数据',
      x: 0.5,
      y: 0.49,
      xref: 'paper',
      yref: 'paper',
      showarrow: false,
      font: { size: 16, color: '#374151' },
      xanchor: 'center' as const,
    },
  ];
}
