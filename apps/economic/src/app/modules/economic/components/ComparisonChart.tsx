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
import {
  BASE_PLOT_CONFIG,
  buildMultiAxisLayout,
  type AxisSpec,
} from '@/lib/utils/plotlyTheme';
import { usePlotlyAutoResize } from '@/lib/hooks/usePlotlyAutoResize';

interface ComparisonChartProps {
  selectedIds: IndicatorId[];
  data: EconomicDataResponse;
}

/** y 轴定义：单轴 + 归一化 0 基线。 */
const AXES: AxisSpec[] = [
  {
    key: 'y',
    title: '归一化值（起点 = 100）',
    axisColor: '#e5e7eb',
    side: 'left',
    zeroline: true,
    zerolinecolor: '#666',
    zerolinewidth: 1,
  },
];

export function ComparisonChart({ selectedIds, data }: ComparisonChartProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
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

    const layout = buildMultiAxisLayout({
      axes: AXES,
      legendX: 1.02,
      margin: { l: 70, r: 180 },
    });
    const config = BASE_PLOT_CONFIG;

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
    <div ref={containerRef} style={{ width: '100%' }}>
      <Plot
        data={traces as never}
        layout={layout}
        config={config}
        style={{ width: '100%', height: '700px' }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}