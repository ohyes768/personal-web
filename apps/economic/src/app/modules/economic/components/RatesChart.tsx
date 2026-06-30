'use client';

/**
 * 利率利差 Tab — Plotly 同图 4 轴叠加
 * - y（左）  ：SOFR + 美债 3M  利率水平（~4-5%）
 * - y2（左内）：TED 利差            信用利差（~0-1%）
 * - y3（右）  ：中国 10y          中国利率水平（~1.5-3%）
 * - y4（右内）：中国 10年-2年       期限利差（~0-1%）
 *
 * 每个指标独立 scale，避免 SOFR（4-5%）和 TED（0-1%）量级差 50 倍导致被压扁
 * 缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';

interface RatesChartProps {
  data: EconomicDataResponse;
}

type NestedKey = [keyof EconomicDataResponse, string];

const RATES_META = {
  sofr:       { label: 'SOFR',          color: '#f472b6', axis: 'y',  unit: '%', dataKey: ['ted_spread', 'sofr']       as NestedKey },
  us_3m:      { label: '美债3M',         color: '#3b82f6', axis: 'y',  unit: '%', dataKey: ['us_treasuries', '3m']       as NestedKey },
  ted_spread: { label: 'TED利差',        color: '#ec4899', axis: 'y2', unit: '%', dataKey: ['ted_spread', 'ted_spread']  as NestedKey },
  cn_10y:     { label: '中国10y',        color: '#f87171', axis: 'y3', unit: '%', dataKey: ['china_bond', '10y']         as NestedKey },
  cn_10y_2y:  { label: '中国10年-2年',   color: '#fb7185', axis: 'y4', unit: '%', dataKey: ['china_bond', 'spread_10y_2y'] as NestedKey },
} as const;

type RatesKey = keyof typeof RATES_META;

/** 嵌套取值：data[key1] 是对象时取 data[key1][key2]，否则取 data[key1] */
function pickSeries(data: EconomicDataResponse, [k1, k2]: NestedKey): (number | null)[] {
  const v1 = data[k1] as unknown;
  if (v1 && typeof v1 === 'object' && !Array.isArray(v1)) {
    const v2 = (v1 as Record<string, unknown>)[k2];
    return Array.isArray(v2) ? (v2 as (number | null)[]) : [];
  }
  return [];
}

export function RatesChart({ data }: RatesChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces: Array<Record<string, unknown>> = (
      Object.keys(RATES_META) as RatesKey[]
    ).map((k) => {
      const meta = RATES_META[k];
      const y = pickSeries(data, meta.dataKey);
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
          `数值: %{y:.3f} ${meta.unit}` +
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
      // 主左轴：SOFR + 美债3M（利率水平）
      yaxis: {
        title: { text: '利率水平 (SOFR / 美债3M, %)', font: { color: '#f472b6' } },
        side: 'left' as const,
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      // 左内：TED 利差
      yaxis2: {
        title: { text: 'TED 利差 (%)', font: { color: '#ec4899' } },
        overlaying: 'y' as const,
        side: 'left' as const,
        position: 0.06,
        showgrid: false,
        color: '#ec4899',
      },
      // 主右轴：中国 10y
      yaxis3: {
        title: { text: '中国 10y (%)', font: { color: '#f87171' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        showgrid: false,
        color: '#f87171',
      },
      // 右内：中国 10年-2年
      yaxis4: {
        title: { text: '中国 10年-2年 (%)', font: { color: '#fb7185' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        position: 0.94,
        showgrid: false,
        color: '#fb7185',
      },
      hovermode: 'x unified' as const,
      paper_bgcolor: '#1a1a1a',
      plot_bgcolor: '#1a1a1a',
      font: { color: '#e5e7eb' },
      showlegend: true,
      legend: {
        orientation: 'v' as const,
        y: 0.5,
        x: 1.06,
        xanchor: 'left' as const,
        yanchor: 'middle' as const,
      },
      margin: { l: 80, r: 220, t: 40, b: 60 },
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