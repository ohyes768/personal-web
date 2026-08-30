'use client';

/**
 * 市场情绪 Tab — 单图双轴
 * 左轴：两市成交额 + 融资余额（亿元）
 * 右轴：换手率（%）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildMultiAxisLayout,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface MarketSentimentChartProps {
  data: EconomicDataResponse;
}

const TRACES = [
  { label: '两市成交额', color: '#f97316', yaxis: 'y' as const, unit: '亿元', dataKey: 'volume' as const, dash: 'solid' as const },
  { label: '融资余额', color: '#22c55e', yaxis: 'y' as const, unit: '亿元', dataKey: 'margin' as const, dash: 'dash' as const },
  { label: '换手率', color: '#eab308', yaxis: 'y2' as const, unit: '%', dataKey: 'turnover' as const, dash: 'solid' as const },
];

export function MarketSentimentChart({ data }: MarketSentimentChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces = TRACES.map((meta) =>
      buildLineTrace(
        {
          label: meta.label,
          color: meta.color,
          unit: meta.unit,
          yaxis: meta.yaxis,
          dash: meta.dash,
          valueFormat: meta.unit === '%' ? '.2f' : ',.0f',
        },
        dates,
        data[meta.dataKey] ?? [],
      ),
    ).filter(Boolean) as Data[];

    const layout = buildMultiAxisLayout({
      axes: [
        {
          key: 'y',
          title: '成交额 / 融资余额 (亿元)',
          titleColor: '#f97316',
          axisColor: '#e5e7eb',
          side: 'left',
        },
        {
          key: 'y2',
          title: '换手率 (%)',
          titleColor: '#eab308',
          axisColor: '#eab308',
          side: 'right',
          overlaying: 'y',
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={1} emptyMessage="暂无市场情绪数据" />;
}
