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

    const layout = {
      xaxis: {
        title: '日期',
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      // 恒生 — 主左轴
      yaxis: {
        title: { text: '恒生指数 (点)', font: { color: '#ef4444' } },
        side: 'left' as const,
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      // 上证 — 左轴次轴（overlay 在 y 上）
      yaxis2: {
        title: { text: '上证指数 (点)', font: { color: '#f59e0b' } },
        overlaying: 'y' as const,
        side: 'left' as const,
        position: 0.06,
        showgrid: false,
        color: '#f59e0b',
      },
      // 标普500 — 第一个右轴
      yaxis3: {
        title: { text: '标普500 (点)', font: { color: '#3b82f6' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        position: 0.92,
        showgrid: false,
        color: '#3b82f6',
      },
      // 纳指 — 右轴
      yaxis4: {
        title: { text: '纳指 (点)', font: { color: '#10b981' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        position: 0.95,
        showgrid: false,
        color: '#10b981',
      },
      // 道指 — 最右轴
      yaxis5: {
        title: { text: '道指 (点)', font: { color: '#a855f7' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        position: 0.98,
        showgrid: false,
        color: '#a855f7',
      },
      hovermode: 'x unified' as const,
      paper_bgcolor: '#1a1a1a',
      plot_bgcolor: '#1a1a1a',
      font: { color: '#e5e7eb' },
      showlegend: true,
      legend: {
        orientation: 'v' as const,
        y: 0.5,
        x: 1.05,
        xanchor: 'left' as const,
        yanchor: 'middle' as const,
      },
      margin: { l: 90, r: 250, t: 40, b: 60 },
    };

    const config = {
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
      doubleClick: 'reset' as const,
    };

    return { traces, layout, config };
  }, [data]);

  return (
    <Plot
      data={traces as never}
      layout={layout as never}
      config={config as never}
      style={{ width: '100%', height: '700px' }}
      className="w-full"
      useResizeHandler
    />
  );
}
