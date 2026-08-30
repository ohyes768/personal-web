'use client';

/**
 * 利率利差 Tab — 3 个联动子图
 * 上：DR007 / SOFR / 美债3M（同单位 %）
 * 中：TED 利差
 * 下：中国 10y + 中国 10年-2年（双轴）
 *
 * 空序列不入图；trace 显式绑定 xaxis/yaxis。
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildLinkedSubplotLayout,
  type AxisKey,
  type XAxisKey,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface RatesChartProps {
  data: EconomicDataResponse;
}

type NestedKey = [keyof EconomicDataResponse, string];
type FlatKey = keyof EconomicDataResponse;

interface TraceMeta {
  label: string;
  color: string;
  yaxis: AxisKey;
  xaxis: XAxisKey;
  dash?: 'solid' | 'dash' | 'dot' | 'dashdot';
  dataKey: NestedKey | FlatKey;
}

const RATES_META: TraceMeta[] = [
  { label: 'DR007', color: '#f97316', yaxis: 'y', xaxis: 'x', dash: 'solid', dataKey: 'dr007' },
  { label: 'SOFR', color: '#3b82f6', yaxis: 'y', xaxis: 'x', dash: 'dash', dataKey: ['ted_spread', 'sofr'] },
  { label: '美债3M', color: '#22c55e', yaxis: 'y', xaxis: 'x', dash: 'dot', dataKey: ['us_treasuries', '3m'] },
  { label: 'TED利差', color: '#ec4899', yaxis: 'y2', xaxis: 'x2', dash: 'solid', dataKey: ['ted_spread', 'ted_spread'] },
  { label: '中国10y', color: '#f87171', yaxis: 'y3', xaxis: 'x3', dash: 'solid', dataKey: ['china_bond', '10y'] },
  { label: '中国10年-2年', color: '#a78bfa', yaxis: 'y4', xaxis: 'x3', dash: 'dash', dataKey: ['china_bond', 'spread_10y_2y'] },
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

export function RatesChart({ data }: RatesChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces = RATES_META.map((meta) =>
      buildLineTrace(
        {
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
    ).filter(Boolean) as Data[];

    const layout = buildLinkedSubplotLayout({
      subplots: [
        {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '短端利率 (%)', titleColor: '#f97316', axisColor: '#e5e7eb', side: 'left' },
          ],
        },
        {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y2', title: 'TED 利差 (%)', titleColor: '#ec4899', axisColor: '#ec4899', side: 'left' },
          ],
        },
        {
          xAxisKey: 'x3',
          yAxes: [
            { key: 'y3', title: '中国 10y (%)', titleColor: '#f87171', axisColor: '#f87171', side: 'left' },
            { key: 'y4', title: '10y-2y (%)', titleColor: '#a78bfa', axisColor: '#a78bfa', side: 'right', overlaying: 'y3' },
          ],
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={3} emptyMessage="暂无利率利差数据" />;
}
