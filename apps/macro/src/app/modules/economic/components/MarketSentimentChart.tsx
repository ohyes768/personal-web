'use client';

/**
 * 市场情绪 Tab — Plotly 单图 3 轴叠加
 *
 * y（左）  ：两市成交额 total_amount_yi   金额（~1-2 万亿元）
 * y2（右） ：换手率 turnover_rate          百分比（~0.5-2%）
 * y3（左内）：融资余额 margin_balance_yi   金额（~2-3 万亿元）
 *
 * 三个指标都是"市场情绪"维度（同涨跌方向），单图叠加比拆 subchart 更符合用户心智。
 * 各 trace 独立 scale，避免成交额/换手率量级差 ~1000 倍被压扁。
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

interface MarketSentimentChartProps {
  data: EconomicDataResponse;
}

const AXES = [
  { key: 'y' as const,  title: '成交额 / 融资余额 (亿元)', titleColor: '#f97316', axisColor: '#e5e7eb', side: 'left' as const },
  { key: 'y2' as const, title: '换手率 (%)',                titleColor: '#eab308', axisColor: '#eab308', side: 'right' as const },
];

interface TraceMeta {
  label: string;
  color: string;
  yaxis: 'y' | 'y2';
  unit: string;
  dataKey: 'volume' | 'turnover' | 'margin';
}

const TRACES: TraceMeta[] = [
  { label: '两市成交额', color: '#f97316', yaxis: 'y',  unit: '亿元', dataKey: 'volume' },
  { label: '换手率',     color: '#eab308', yaxis: 'y2', unit: '%',    dataKey: 'turnover' },
  { label: '融资余额',   color: '#22c55e', yaxis: 'y',  unit: '亿元', dataKey: 'margin' },
];

function buildAxisDef(axis: typeof AXES[number], isMain: boolean) {
  const titleObj = { text: axis.title, font: { color: axis.titleColor } };
  return {
    title: titleObj,
    side: axis.side,
    showgrid: isMain,
    gridcolor: PLOTLY_DARK.gridColor,
    color: axis.axisColor,
  };
}

export function MarketSentimentChart({ data }: MarketSentimentChartProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];
    const traces: Data[] = TRACES.map((meta) => {
      const series = data[meta.dataKey] ?? [];
      return {
        type: 'scatter',
        mode: 'lines',
        name: meta.label,
        x: dates,
        y: series,
        yaxis: meta.yaxis,
        line: { color: meta.color, width: 2 },
        hovertemplate:
          `<b>${meta.label}</b><br>` +
          `日期: %{x}<br>` +
          `数值: %{y:.2f} ${meta.unit}` +
          `<extra></extra>`,
        connectgaps: false,
      } as Data;
    });

    const layout: Partial<Layout> = {
      xaxis: {
        title: '日期',
        showgrid: true,
        gridcolor: PLOTLY_DARK.gridColor,
        color: PLOTLY_DARK.fontColor,
      },
      yaxis: buildAxisDef(AXES[0], true),
      yaxis2: buildAxisDef(AXES[1], false),
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