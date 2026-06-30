'use client';

/**
 * 股指 Tab — Plotly 同图 5 轴叠加
 * - y（左）   ：恒生指数    HKHSI    ~20000
 * - y2（左内）：上证指数    SH000001 ~3000
 * - y3（右）  ：标普500    SPX      ~5000
 * - y4（右）  ：纳斯达克    IXIC     ~15000
 * - y5（右）  ：道琼斯      DJI      ~40000
 *
 * 每个指数独立 scale，避免数值差异太大导致曲线被压扁
 * - 历史缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  buildMultiAxisLayout,
  type AxisSpec,
} from '@/lib/utils/plotlyTheme';

interface StockIndexChartProps {
  data: EconomicDataResponse;
}

const INDEX_META = {
  HKHSI:    { label: '恒生指数', color: '#ef4444', axis: 'y',  unit: '点' },
  SH000001: { label: '上证指数', color: '#f59e0b', axis: 'y2', unit: '点' },
  SPX:      { label: '标普500',  color: '#3b82f6', axis: 'y3', unit: '点' },
  IXIC:     { label: '纳斯达克', color: '#10b981', axis: 'y4', unit: '点' },
  DJI:      { label: '道琼斯',   color: '#a855f7', axis: 'y5', unit: '点' },
} as const;

type IndexKey = keyof typeof INDEX_META;

/** y 轴定义：title/titleColor/axisColor/side/overlaying/position。 */
const AXES: AxisSpec[] = [
  { key: 'y',  title: '恒生指数 (点)', titleColor: '#ef4444', axisColor: '#ef4444', side: 'left' },
  { key: 'y2', title: '上证指数 (点)', titleColor: '#f59e0b', axisColor: '#f59e0b', side: 'left',  overlaying: 'y', position: 0.06 },
  { key: 'y3', title: '标普500 (点)',  titleColor: '#3b82f6', axisColor: '#3b82f6', side: 'right', overlaying: 'y', position: 0.92 },
  { key: 'y4', title: '纳指 (点)',     titleColor: '#10b981', axisColor: '#10b981', side: 'right', overlaying: 'y', position: 0.95 },
  { key: 'y5', title: '道指 (点)',     titleColor: '#a855f7', axisColor: '#a855f7', side: 'right', overlaying: 'y', position: 0.98 },
];

export function StockIndexChart({ data }: StockIndexChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];
    const indices = data.indices;

    const traces: Array<Record<string, unknown>> = (
      Object.keys(INDEX_META) as IndexKey[]
    ).map((k) => {
      const meta = INDEX_META[k];
      const y = indices?.[k] ?? [];
      return {
        type: 'scatter',
        mode: 'lines',
        name: meta.label,
        x: dates,
        y,
        yaxis: meta.axis,
        line: { color: meta.color, width: 2 },
        hovertemplate:
          `<b>${meta.label}</b><br>` +
          `日期: %{x}<br>` +
          `点位: %{y:.2f} ${meta.unit}` +
          `<extra></extra>`,
        connectgaps: false,
      };
    });

    const layout = buildMultiAxisLayout({
      axes: AXES,
      legendX: 1.05,
      margin: { l: 90, r: 250 },
    });
    const config = BASE_PLOT_CONFIG;

    return { traces, layout, config };
  }, [data]);

  return (
    <Plot
      data={traces as never}
      layout={layout}
      config={config}
      style={{ width: '100%', height: '700px' }}
      className="w-full"
      useResizeHandler
    />
  );
}