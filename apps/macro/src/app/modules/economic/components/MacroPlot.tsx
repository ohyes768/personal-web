/**
 * 宏观页 Plotly 统一包装：
 * - hidden Tab 显示后自动 resize
 * - 统一 config / 默认高度
 * - 不拼业务 traces，只负责渲染壳
 */
'use client';

import Plot from 'react-plotly.js';
import type { Config, Data, Layout } from 'plotly.js';
import { usePlotlyAutoResize } from '@/lib/hooks/usePlotlyAutoResize';
import {
  BASE_PLOT_CONFIG,
  chartHeightForSubplots,
} from '@/lib/utils/plotlyTheme';

interface MacroPlotProps {
  data: Data[];
  layout: Partial<Layout>;
  /** 子图数量，用于估算默认高度 */
  subplotCount?: number;
  /** 显式高度优先于 subplotCount 估算 */
  height?: number;
  config?: Partial<Config>;
  className?: string;
  emptyMessage?: string;
}

export function MacroPlot({
  data,
  layout,
  subplotCount = 1,
  height,
  config,
  className,
  emptyMessage = '暂无可用数据',
}: MacroPlotProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
  const resolvedHeight = height ?? chartHeightForSubplots(subplotCount);

  if (!data.length) {
    return (
      <div
        ref={containerRef}
        className={className}
        style={{ width: '100%', height: resolvedHeight }}
      >
        <div className="h-full flex items-center justify-center rounded-lg border border-gray-800 bg-gray-900 text-gray-400">
          {emptyMessage}
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={className} style={{ width: '100%' }}>
      <Plot
        data={data}
        layout={layout}
        config={{ ...BASE_PLOT_CONFIG, ...config }}
        style={{ width: '100%', height: resolvedHeight }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}
