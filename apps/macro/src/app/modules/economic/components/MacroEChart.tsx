'use client';

import { useChartAnalysis } from './analysis/AnalysisProvider';
import { useEffect, useMemo, useRef, useState } from 'react';
import { init, use, type EChartsType } from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { buildEChartsOption, chartDates, clampRange, dateRangeFromZoom } from '@/lib/utils/echartsOptions';
import { chartHeightForSubplots, lastValidDate, type ChartContext, type ChartLayout, type ChartSeries, type DateRange } from '@/lib/utils/chartTheme';

use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer]);
interface MacroEChartProps {
  data: ChartSeries[]; layout: ChartLayout; chartId: string;
  subplotCount?: number; height?: number; className?: string; emptyMessage?: string;
  range?: DateRange; onRangeChange?: (range: DateRange) => void;
  onContextChange?: (context: ChartContext) => void;
}
export function MacroEChart({
  data, layout, chartId, subplotCount = 1, height, className,
  emptyMessage = '暂无可用数据', range, onRangeChange, onContextChange,
}: MacroEChartProps) {
  const analysis = useChartAnalysis();
  const analysisDefinition = analysis?.definitions.find(definition => definition.id === chartId);
  const registerAnalysis = analysis?.register;
  const revision = useMemo(() => {
    let hash = 2166136261;
    const text = JSON.stringify(data.map(line => [line.id, line.dates, line.values, line.transform, line.scaleFactor, line.details]));
    for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
    return (hash >>> 0).toString(16);
  }, [data]);
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<EChartsType | null>(null);
  const [localRange, setLocalRange] = useState<DateRange>(null);
  const [narrow, setNarrow] = useState(false);
  const [hiddenIds, setHiddenIds] = useState<string[]>([]);
  const [renderError, setRenderError] = useState(false);
  const hasData = data.length > 0;
  const resolvedRange = range === undefined ? localRange : range;
  const dates = useMemo(() => chartDates(data), [data]);
  const datesRef = useRef(dates);
  datesRef.current = dates;
  const callbacks = useRef({ onRangeChange, onContextChange });
  callbacks.current = { onRangeChange, onContextChange };
  const option = useMemo(() => {
    const result = buildEChartsOption(data, layout, resolvedRange, narrow);
    result.legend = { show: false, selected: Object.fromEntries(data.map((line) => [line.name, !hiddenIds.includes(line.id)])) };
    return result;
  }, [data, layout, resolvedRange, narrow, hiddenIds]);
  const optionRef = useRef(option);
  optionRef.current = option;

  useEffect(() => {
    setLocalRange(null);
  }, [data]);
  useEffect(() => {
    const context: ChartContext = {
      chartId, series: data.map((line) => ({ id: line.id, label: line.name, unit: line.unit, transform: line.transform, ...(line.scaleFactor ? { scaleFactor: line.scaleFactor } : {}) })),
      dateRange: clampRange(dates, resolvedRange) ?? (dates.length ? [dates[0], dates[dates.length - 1]] : null),
    };
    callbacks.current.onContextChange?.(context);
    registerAnalysis?.(context, revision);
  }, [chartId, data, dates, resolvedRange, registerAnalysis, revision]);

  useEffect(() => {
    const element = container.current;
    if (!element || !hasData) return;
    let disposed = false;
    const resize = () => {
      if (disposed || !element.clientWidth || !element.clientHeight) return;
      setNarrow(element.clientWidth < 500);
      try {
        if (!instance.current) {
          const chart = init(element, undefined, { renderer: 'canvas' });
          instance.current = chart;
          chart.on('datazoom', () => {
            const state = chart.getOption().dataZoom as { start?: number; end?: number }[];
            const next = dateRangeFromZoom(datesRef.current, state[0]?.start, state[0]?.end);
            setLocalRange(next);
            callbacks.current.onRangeChange?.(next);
          });
          chart.setOption(optionRef.current, { notMerge: true });
        }
        instance.current.resize();
      } catch (error) {
        console.error('宏观图表渲染失败', chartId, error);
        setRenderError(true);
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    return () => { disposed = true; observer.disconnect(); instance.current?.dispose(); instance.current = null; };
  }, [chartId, hasData]);
  useEffect(() => {
    if (!instance.current) return;
    try { instance.current.setOption(option, { notMerge: true, silent: true }); setRenderError(false); }
    catch (error) { console.error('宏观图表更新失败', chartId, error); setRenderError(true); }
  }, [option, chartId]);
  const reset = () => { setLocalRange(null); callbacks.current.onRangeChange?.(null); };
  const latest = lastValidDate(data);
  return (
    <section className={className} data-chart-id={chartId} data-range={JSON.stringify(resolvedRange)}>
      {analysisDefinition && <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <h3 className="text-sm font-medium text-gray-200">{analysisDefinition.title}</h3>
        <div className="flex gap-2">
          <button type="button" onClick={() => analysis?.open(chartId, true)} className="text-xs text-gray-400 border border-gray-700 rounded px-3 py-2">指标说明</button>
          <button type="button" disabled={!hasData} onClick={() => analysis?.open(chartId)} className="text-xs text-sky-200 bg-sky-950 border border-sky-800 rounded px-3 py-2 disabled:opacity-40">帮我分析</button>
        </div>
      </div>}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2 text-xs">
        <div className="flex flex-wrap gap-x-3 gap-y-2" aria-label="曲线图例">
          {data.map((line) => (
            <button key={line.id} type="button" aria-pressed={!hiddenIds.includes(line.id)}
              className={`flex items-center gap-1.5 ${hiddenIds.includes(line.id) ? 'opacity-40' : ''}`}
              onClick={() => setHiddenIds((old) => old.includes(line.id) ? old.filter((id) => id !== line.id) : [...old, line.id])}>
              <span className="inline-block w-4 border-t-2" style={{ borderColor: line.color, borderStyle: line.dash === 'solid' ? 'solid' : 'dashed' }} />
              <span className="text-gray-200">{line.name}</span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-gray-500">
          {latest && <span>截至 {latest}</span>}
          <button type="button" onClick={reset} className="text-gray-400 hover:text-white">复位</button>
        </div>
      </div>
      <div className="flex flex-wrap justify-between gap-2 text-xs mb-1">
        {layout.axes.map((axis) => <span key={axis.key} style={{ color: axis.titleColor ?? axis.axisColor }}>{axis.title}</span>)}
      </div>
      <div className="relative" style={{ height: height ?? chartHeightForSubplots(subplotCount), width: '100%' }}>
        <div ref={container} className="w-full h-full" onDoubleClick={reset} role="img" aria-label={layout.title ?? data.map((line) => line.name).join('、')} />
        {(!data.length || renderError) && <div className="absolute inset-0 flex items-center justify-center rounded border border-gray-800 bg-gray-900 text-gray-400">{renderError ? '图表加载失败，请刷新重试' : emptyMessage}</div>}
      </div>
    </section>
  );
}
