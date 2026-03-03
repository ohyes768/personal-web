/**
 * Plotly 图表配置工具函数
 */
import type { ChartTrace, ChartColors } from '../types/economic';

/** 图表颜色配置 */
export const CHART_COLORS: ChartColors = {
  treasury3M: '#3B82F6',  // 蓝色
  treasury2Y: '#10B981',  // 绿色
  treasury10Y: '#F59E0B', // 橙色
  dollarIndex: '#8B5CF6', // 紫色
  usdCny: '#EF4444',      // 红色
  usdJpy: '#EC4899',      // 粉色
  usdEur: '#06B6D4',      // 青色
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
 * 生成汇率图表数据系列
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
      y: data.dollar_index,
      name: '美元指数',
      mode: 'lines',
      line: { color: CHART_COLORS.dollarIndex, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: data.usd_cny,
      name: 'USD/CNY',
      mode: 'lines',
      line: { color: CHART_COLORS.usdCny, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: data.usd_jpy,
      name: 'USD/JPY',
      mode: 'lines',
      line: { color: CHART_COLORS.usdJpy, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
    {
      x: dates,
      y: data.usd_eur,
      name: 'USD/EUR',
      mode: 'lines',
      line: { color: CHART_COLORS.usdEur, width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
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
      rows: 2,
      columns: 1,
      pattern: 'independent',
    },
    // 美债收益率图
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
    // 汇率图
    xaxis2: {
      title: '日期',
      anchor: 'y2',
      showgrid: true,
      gridcolor: gridColor,
      color: textColor,
    },
    yaxis2: {
      title: '汇率',
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
    vertical_spacing: 0.15,
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
