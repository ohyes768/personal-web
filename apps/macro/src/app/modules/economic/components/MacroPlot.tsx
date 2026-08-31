/**
 * 宏观页 Plotly 统一包装：
 * - hidden Tab 显示后自动 resize
 * - 把 height/autosize 写入 layout，避免 hidden 容器首次 newPlot 得到 0 高图
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
  /** Plotly relayout 事件透传（联动子图用于同步 x 轴范围） */
  onRelayout?: (e: Record<string, unknown>) => void;
  /** react-plotly.js 默认静默吞掉 Plotly.react 抛错，传入以暴露 */
  onError?: (err: unknown) => void;
}

export function MacroPlot({
  data,
  layout,
  subplotCount = 1,
  height,
  config,
  className,
  emptyMessage = '暂无可用数据',
  onRelayout,
  onError,
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

  const mergedLayout: Partial<Layout> = {
    ...layout,
    autosize: true,
    height: layout.height ?? resolvedHeight,
  };

  return (
    <div ref={containerRef} className={className} style={{ width: '100%' }}>
      <Plot
        data={data}
        layout={mergedLayout}
        config={{ ...BASE_PLOT_CONFIG, ...config }}
        style={{ width: '100%', height: resolvedHeight }}
        className="w-full"
        useResizeHandler
        onRelayout={onRelayout}
        onError={onError}
      />
    </div>
  );
}
