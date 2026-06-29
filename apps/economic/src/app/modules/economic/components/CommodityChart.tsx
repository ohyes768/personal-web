'use client';

/**
 * 商品 Tab — Plotly 同图双轴叠加
 * - 左轴（y）：黄金 / 白银（元/克）
 * - 右轴（y2）：原油（$/桶）/ 铜（$/吨）
 * - 4 条曲线展示各商品价格走势
 * - 历史 silver 缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';

interface CommodityChartProps {
  data: EconomicDataResponse;
}

const COMMODITY_META = {
  gold:   { label: '黄金', color: '#eab308', axis: 'y',  unit: '元/克' },
  silver: { label: '白银', color: '#94a3b8', axis: 'y',  unit: '元/克' },
  oil:    { label: '原油', color: '#1e293b', axis: 'y2', unit: '$/桶' },
  copper: { label: '铜',   color: '#b45309', axis: 'y2', unit: '$/吨' },
} as const;

type CommodityKey = keyof typeof COMMODITY_META;

export function CommodityChart({ data }: CommodityChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];
    const commodities = data.commodities;

    const traces: Array<Record<string, unknown>> = (
      Object.keys(COMMODITY_META) as CommodityKey[]
    ).map((k) => {
      const meta = COMMODITY_META[k];
      const y = commodities?.[k] ?? [];
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
          `价格: %{y:.2f} ${meta.unit}` +
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
      yaxis: {
        title: '左轴：黄金/白银（元/克）',
        side: 'left' as const,
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      yaxis2: {
        title: '右轴：原油($/桶) / 铜($/吨)',
        overlaying: 'y' as const,
        side: 'right' as const,
        showgrid: false,
        color: '#e5e7eb',
      },
      hovermode: 'x unified' as const,
      paper_bgcolor: '#1a1a1a',
      plot_bgcolor: '#1a1a1a',
      font: { color: '#e5e7eb' },
      showlegend: true,
      legend: {
        orientation: 'v' as const,
        y: 0.5,
        x: 1.02,
        xanchor: 'left' as const,
        yanchor: 'middle' as const,
      },
      margin: { l: 80, r: 200, t: 40, b: 60 },
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