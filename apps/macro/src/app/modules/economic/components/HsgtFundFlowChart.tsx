'use client';

/**
 * 沪深港通资金图 — Plotly 双轴叠加
 *
 * y（左） ：北向成交额 north_deal_amount   金额（~1000-3000 亿元，恒正，外资活跃度）
 * y2（右）：南向净流入 south_net_flow      金额（可正可负，±数百亿，内资方向）
 *
 * 北向净买额 2024-08 起停发，改看成交额（活跃度）；南向仍每日公布净买额（方向）。
 * 两指标量级相近但符号语义不同（活跃度 vs 方向），双轴 + 南向 0 线参考最直观。
 * 缺失段 Plotly connectgaps=false 自动断开。
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { Layout, Config, Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  PLOTLY_DARK,
} from '@/lib/utils/plotlyTheme';
import { usePlotlyAutoResize } from '@/lib/hooks/usePlotlyAutoResize';

interface HsgtFundFlowChartProps {
  data: EconomicDataResponse;
}

interface TraceMeta {
  label: string;
  color: string;
  yaxis: 'y' | 'y2';
  unit: string;
  series: (number | null)[] | undefined;
}

export function HsgtFundFlowChart({ data }: HsgtFundFlowChartProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];
    const tracesMeta: TraceMeta[] = [
      { label: '北向成交额', color: '#06b6d4', yaxis: 'y',  unit: '亿元', series: data.fund_flow?.north_deal_amount },
      { label: '南向净流入', color: '#22d3ee', yaxis: 'y2', unit: '亿元', series: data.fund_flow?.south_net_flow },
    ];
    const traces: Data[] = tracesMeta.map((meta) => ({
      type: 'scatter',
      mode: 'lines',
      name: meta.label,
      x: dates,
      y: meta.series ?? [],
      yaxis: meta.yaxis,
      line: { color: meta.color, width: 2 },
      hovertemplate:
        `<b>${meta.label}</b><br>` +
        `日期: %{x}<br>` +
        `数值: %{y:.2f} ${meta.unit}` +
        `<extra></extra>`,
      connectgaps: false,
    })) as Data[];

    const layout: Partial<Layout> = {
      xaxis: {
        title: '日期',
        showgrid: true,
        gridcolor: PLOTLY_DARK.gridColor,
        color: PLOTLY_DARK.fontColor,
      },
      yaxis: {
        title: { text: '北向成交额 (亿元)', font: { color: '#06b6d4' } },
        side: 'left',
        showgrid: true,
        gridcolor: PLOTLY_DARK.gridColor,
        color: '#e5e7eb',
      },
      yaxis2: {
        title: { text: '南向净流入 (亿元)', font: { color: '#22d3ee' } },
        side: 'right',
        overlaying: 'y',
        showgrid: false,
        zeroline: true,
        zerolinecolor: PLOTLY_DARK.gridColor,
        zerolinewidth: 1,
        color: '#22d3ee',
      },
      hovermode: 'x unified',
      paper_bgcolor: PLOTLY_DARK.paper_bgcolor,
      plot_bgcolor: PLOTLY_DARK.plot_bgcolor,
      font: { color: PLOTLY_DARK.fontColor },
      showlegend: true,
      legend: {
        orientation: 'v',
        y: 0.5,
        x: 1.02,
        xanchor: 'left',
        yanchor: 'middle',
      },
      margin: { l: 80, r: 180, t: 30, b: 50 },
      height: 700,
    } as Partial<Layout>;

    const config: Partial<Config> = BASE_PLOT_CONFIG;
    return { traces, layout, config };
  }, [data]);

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <Plot
        data={traces}
        layout={layout}
        config={config}
        style={{ width: '100%', height: '700px' }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}
