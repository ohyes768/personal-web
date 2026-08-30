'use client';

/**
 * 股指 Tab — 3 个联动子图
 * 上：恒生 + 上证
 * 中：标普500 + 纳斯达克
 * 下：道琼斯
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildLinkedSubplotLayout,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface StockIndexChartProps {
  data: EconomicDataResponse;
}

const META = {
  HKHSI:    { label: '恒生指数', color: '#ef4444', dash: 'solid' as const },
  SH000001: { label: '上证指数', color: '#f59e0b', dash: 'dash' as const },
  SPX:      { label: '标普500',  color: '#3b82f6', dash: 'solid' as const },
  IXIC:     { label: '纳斯达克', color: '#10b981', dash: 'dash' as const },
  DJI:      { label: '道琼斯',   color: '#a855f7', dash: 'solid' as const },
} as const;

export function StockIndexChart({ data }: StockIndexChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];
    const indices = data.indices;

    const traces = [
      buildLineTrace(
        { label: META.HKHSI.label, color: META.HKHSI.color, unit: '点', yaxis: 'y', xaxis: 'x', dash: META.HKHSI.dash, valueFormat: ',.0f' },
        dates,
        indices?.HKHSI ?? [],
      ),
      buildLineTrace(
        { label: META.SH000001.label, color: META.SH000001.color, unit: '点', yaxis: 'y2', xaxis: 'x', dash: META.SH000001.dash, valueFormat: ',.0f' },
        dates,
        indices?.SH000001 ?? [],
      ),
      buildLineTrace(
        { label: META.SPX.label, color: META.SPX.color, unit: '点', yaxis: 'y3', xaxis: 'x2', dash: META.SPX.dash, valueFormat: ',.0f' },
        dates,
        indices?.SPX ?? [],
      ),
      buildLineTrace(
        { label: META.IXIC.label, color: META.IXIC.color, unit: '点', yaxis: 'y4', xaxis: 'x2', dash: META.IXIC.dash, valueFormat: ',.0f' },
        dates,
        indices?.IXIC ?? [],
      ),
      buildLineTrace(
        { label: META.DJI.label, color: META.DJI.color, unit: '点', yaxis: 'y5', xaxis: 'x3', dash: META.DJI.dash, valueFormat: ',.0f' },
        dates,
        indices?.DJI ?? [],
      ),
    ].filter(Boolean) as Data[];

    const layout = buildLinkedSubplotLayout({
      subplots: [
        {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '恒生 (点)', titleColor: META.HKHSI.color, axisColor: META.HKHSI.color, side: 'left' },
            { key: 'y2', title: '上证 (点)', titleColor: META.SH000001.color, axisColor: META.SH000001.color, side: 'right', overlaying: 'y' },
          ],
        },
        {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y3', title: '标普500 (点)', titleColor: META.SPX.color, axisColor: META.SPX.color, side: 'left' },
            { key: 'y4', title: '纳指 (点)', titleColor: META.IXIC.color, axisColor: META.IXIC.color, side: 'right', overlaying: 'y3' },
          ],
        },
        {
          xAxisKey: 'x3',
          yAxes: [
            { key: 'y5', title: '道指 (点)', titleColor: META.DJI.color, axisColor: META.DJI.color, side: 'left' },
          ],
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={3} />;
}
