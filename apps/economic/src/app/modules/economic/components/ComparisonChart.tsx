'use client';

/**
 * 对比模块 — Plotly 单子图 + 归一化叠加
 * 所有曲线起点归一为 100，Y 轴显示相对涨跌 %
 * 悬停 tooltip 显示归一化值 + 原始值 + 涨跌幅
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { INDICATORS } from '@/lib/modules/comparison/indicators';
import { extractSeries, normalize } from '@/lib/modules/comparison/normalize';
import type { IndicatorId } from '@/lib/modules/comparison/types';

interface ComparisonChartProps {
  selectedIds: IndicatorId[];
  data: EconomicDataResponse;
}

export function ComparisonChart({ selectedIds, data }: ComparisonChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates;

    // 构造每个 trace
    const traces: Array<Record<string, unknown>> = selectedIds.map((id) => {
      const meta = INDICATORS[id];
      const raw = extractSeries(data, id);
      const norm = normalize(raw);

      // customdata 用于 tooltip：传原始值
      return {
        type: 'scatter',
        mode: 'lines',
        name: meta.label,
        x: dates,
        y: norm,
        customdata: raw,
        line: { color: meta.color, width: 2 },
        hovertemplate:
          `<b>${meta.label}</b><br>` +
          `日期: %{x}<br>` +
          `原始值: %{customdata}${meta.unit ? ' ' + meta.unit : ''}<br>` +
          `归一化: %{y:.2f}<br>` +
          `涨跌: %{y - 100:+.2f}%` +
          `<extra></extra>`,
        connectgaps: false,  // null 值断开，不画虚线（欧债日债月级时友好）
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
        title: '归一化值（起点 = 100）',
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
        zeroline: true,
        zerolinecolor: '#666',
        zerolinewidth: 1,
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
      margin: { l: 70, r: 180, t: 40, b: 60 },
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
  }, [selectedIds, data]);

  if (selectedIds.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
        <p className="text-gray-400 text-lg">请至少选择 1 个指标开始对比</p>
      </div>
    );
  }

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
