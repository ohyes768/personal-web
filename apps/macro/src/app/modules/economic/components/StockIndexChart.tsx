'use client';

/**
 * 股指 Tab — 3 个联动子图（独立 Plot 实例）
 * 上：恒生 + 上证
 * 中：标普500 + 纳斯达克
 * 下：道琼斯
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  type SubplotPanelSpec,
} from '@/lib/utils/plotlyTheme';
import { LinkedSubplots } from './LinkedSubplots';

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

function tracesOf(...items: Array<Data | null>): Data[] {
  return items.filter((t): t is Data => t != null);
}

export function StockIndexChart({ data }: StockIndexChartProps) {
  const subplots = useMemo<SubplotPanelSpec[]>(() => {
    const dates = data.dates ?? [];
    const indices = data.indices;

    const line = (
      key: keyof typeof META,
      yaxis: 'y' | 'y2' | 'y3' | 'y4' | 'y5',
      xaxis: 'x' | 'x2' | 'x3',
    ) =>
      buildLineTrace(
        {
          label: META[key].label,
          color: META[key].color,
          unit: '点',
          yaxis,
          xaxis,
          dash: META[key].dash,
          valueFormat: ',.0f',
        },
        dates,
        indices?.[key] ?? [],
      );

    return [
      {
        traces: tracesOf(line('HKHSI', 'y', 'x'), line('SH000001', 'y2', 'x')),
        spec: {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '恒生 (点)', titleColor: META.HKHSI.color, axisColor: META.HKHSI.color, side: 'left' },
            { key: 'y2', title: '上证 (点)', titleColor: META.SH000001.color, axisColor: META.SH000001.color, side: 'right', overlaying: 'y' },
          ],
        },
        emptyMessage: '暂无港股/A 股指数',
      },
      {
        traces: tracesOf(line('SPX', 'y3', 'x2'), line('IXIC', 'y4', 'x2')),
        spec: {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y3', title: '标普500 (点)', titleColor: META.SPX.color, axisColor: META.SPX.color, side: 'left' },
            { key: 'y4', title: '纳指 (点)', titleColor: META.IXIC.color, axisColor: META.IXIC.color, side: 'right', overlaying: 'y3' },
          ],
        },
        emptyMessage: '暂无美股成长指数',
      },
      {
        traces: tracesOf(line('DJI', 'y5', 'x3')),
        spec: {
          xAxisKey: 'x3',
          yAxes: [
            { key: 'y5', title: '道指 (点)', titleColor: META.DJI.color, axisColor: META.DJI.color, side: 'left' },
          ],
        },
        emptyMessage: '暂无道琼斯数据',
      },
    ];
  }, [data]);

  return <LinkedSubplots subplots={subplots} />;
}
