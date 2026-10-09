'use client';

/**
 * 利率利差 Tab — 3 个联动子图（独立 Plot 实例）
 * 上：DR007 / SOFR / 美债3M（同单位 %）
 * 中：TED 利差
 * 下：中国 10y + 中国 10年-2年（双轴）
 *
 * 空序列不入图；trace 显式绑定 xaxis/yaxis。
 */
import { useMemo } from 'react';
import type { ChartContext } from '@/lib/utils/chartTheme';
import type { ChartSeries } from '@/lib/utils/chartTheme';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  type AxisKey,
  type SubplotPanelSpec,
  type XAxisKey,
} from '@/lib/utils/chartTheme';
import { LinkedSubplots } from './LinkedSubplots';

interface RatesChartProps {
  onContextChange?: (context: ChartContext) => void;
  data: EconomicDataResponse;
}

type NestedKey = [keyof EconomicDataResponse, string];
type FlatKey = keyof EconomicDataResponse;

interface TraceMeta {
  id: string;
  label: string;
  color: string;
  yaxis: AxisKey;
  xaxis: XAxisKey;
  dash?: 'solid' | 'dash' | 'dot' | 'dashdot';
  dataKey: NestedKey | FlatKey;
}

const RATES_META: TraceMeta[] = [
  { id: 'dr007', label: 'DR007', color: '#f97316', yaxis: 'y', xaxis: 'x', dash: 'solid', dataKey: 'dr007' },
  { id: 'sofr', label: 'SOFR', color: '#3b82f6', yaxis: 'y', xaxis: 'x', dash: 'dash', dataKey: ['ted_spread', 'sofr'] },
  { id: 'us_3m', label: '美债3M', color: '#22c55e', yaxis: 'y', xaxis: 'x', dash: 'dot', dataKey: ['us_treasuries', '3m'] },
  { id: 'ted_spread', label: 'TED利差', color: '#ec4899', yaxis: 'y2', xaxis: 'x2', dash: 'solid', dataKey: ['ted_spread', 'ted_spread'] },
  { id: 'cn_10y', label: '中国10y', color: '#f87171', yaxis: 'y3', xaxis: 'x3', dash: 'solid', dataKey: ['china_bond', '10y'] },
  { id: 'cn_10y_2y', label: '中国10年-2年', color: '#a78bfa', yaxis: 'y4', xaxis: 'x3', dash: 'dash', dataKey: ['china_bond', 'spread_10y_2y'] },
];

function pickSeries(data: EconomicDataResponse, dataKey: NestedKey | FlatKey): (number | null)[] {
  if (typeof dataKey === 'string') {
    const v = data[dataKey] as unknown;
    return Array.isArray(v) ? (v as (number | null)[]) : [];
  }
  const [k1, k2] = dataKey;
  const v1 = data[k1] as unknown;
  if (v1 && typeof v1 === 'object' && !Array.isArray(v1)) {
    const v2 = (v1 as Record<string, unknown>)[k2];
    return Array.isArray(v2) ? (v2 as (number | null)[]) : [];
  }
  return [];
}

function tracesOf(dates: string[], data: EconomicDataResponse, metas: TraceMeta[]): ChartSeries[] {
  return metas
    .map((meta) =>
      buildLineTrace(
        {
          id: meta.id,
          label: meta.label,
          color: meta.color,
          unit: '%',
          yaxis: meta.yaxis,
          xaxis: meta.xaxis,
          dash: meta.dash,
          valueFormat: '.3f',
        },
        dates,
        pickSeries(data, meta.dataKey),
      ),
    )
    .filter((t): t is ChartSeries => t != null);
}

export function RatesChart({ data, onContextChange }: RatesChartProps) {
  const subplots = useMemo<SubplotPanelSpec[]>(() => {
    const dates = data.dates ?? [];

    return [
      {
        id: 'rates.short-rates',
        traces: tracesOf(dates, data, RATES_META.filter((m) => m.xaxis === 'x')),
        spec: {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '短端利率 (%)', titleColor: '#f97316', axisColor: '#e5e7eb', side: 'left' },
          ],
        },
        emptyMessage: '暂无短端利率数据',
      },
      {
        id: 'rates.ted',
        traces: tracesOf(dates, data, RATES_META.filter((m) => m.xaxis === 'x2')),
        spec: {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y2', title: 'TED 利差 (%)', titleColor: '#ec4899', axisColor: '#ec4899', side: 'left' },
          ],
        },
        emptyMessage: '暂无 TED 利差数据',
      },
      {
        id: 'rates.china-bonds',
        traces: tracesOf(dates, data, RATES_META.filter((m) => m.xaxis === 'x3')),
        spec: {
          xAxisKey: 'x3',
          yAxes: [
            { key: 'y3', title: '中国 10y (%)', titleColor: '#f87171', axisColor: '#f87171', side: 'left' },
            { key: 'y4', title: '10y-2y (%)', titleColor: '#a78bfa', axisColor: '#a78bfa', side: 'right', overlaying: 'y3' },
          ],
        },
        emptyMessage: '暂无中国国债数据',
      },
    ];
  }, [data]);

  return <LinkedSubplots onContextChange={onContextChange} chartId="rates" subplots={subplots} />;
}
