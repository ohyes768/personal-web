/**
 * 经济数据图表组件 — 中美利差 / 汇率
 * 上图：美债 + 中国10y（收益率 %）
 * 下图：汇率相对变化 %（tooltip 同时显示原始汇率）
 */
'use client';

import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildLinkedSubplotLayout,
  hasValidPoints,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface EconomicChartProps {
  data: EconomicDataResponse;
  showAllData?: boolean;
}

function relativeChange(values: Array<number | null | undefined>): Array<number | null> {
  const base = values.find((v) => v != null && !Number.isNaN(v as number));
  if (base == null) return values.map(() => null);
  return values.map((v) => {
    if (v == null || Number.isNaN(v as number)) return null;
    return (((v as number) - (base as number)) / (base as number)) * 100;
  });
}

export function EconomicChart({ data }: EconomicChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];
    const us = data.us_treasuries;
    const china = data.china_bond;
    const fx = data.exchange_rates;

    const traces: Data[] = [];

    const pushRate = (
      label: string,
      color: string,
      series: Array<number | null | undefined> | undefined,
      dash: 'solid' | 'dash' | 'dot' = 'solid',
    ) => {
      const t = buildLineTrace(
        { label, color, unit: '%', yaxis: 'y', xaxis: 'x', dash, valueFormat: '.3f' },
        dates,
        series ?? [],
      );
      if (t) traces.push(t);
    };

    pushRate('美债3M', '#3b82f6', us?.['3m'], 'dot');
    pushRate('美债2Y', '#10b981', us?.['2y'], 'dash');
    pushRate('美债10Y', '#f59e0b', us?.['10y'], 'solid');
    pushRate('中国10Y', '#fbbf24', china?.['10y'], 'dash');

    const pushFx = (
      label: string,
      color: string,
      series: Array<number | null | undefined> | undefined,
      dash: 'solid' | 'dash' | 'dot' = 'solid',
    ) => {
      const raw = series ?? [];
      if (!hasValidPoints(raw)) return;
      const rel = relativeChange(raw);
      const t = buildLineTrace(
        { label, color, unit: '%', yaxis: 'y2', xaxis: 'x2', dash, valueFormat: '.2f' },
        dates,
        rel,
        {
          customdata: raw as unknown[],
          hovertemplate:
            `<b>${label}</b><br>` +
            `相对变化: %{y:.2f}%<br>` +
            `原始值: %{customdata:.4f}` +
            `<extra></extra>`,
        },
      );
      if (t) traces.push(t);
    };

    pushFx('美元指数', '#06b6d4', fx?.dollar_index, 'solid');
    pushFx('USD/CNY', '#ec4899', fx?.usd_cny, 'dash');
    pushFx('USD/JPY', '#a78bfa', fx?.usd_jpy, 'dot');
    pushFx('USD/EUR', '#34d399', fx?.usd_eur, 'dash');

    const layout = buildLinkedSubplotLayout({
      subplots: [
        {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '收益率 (%)', titleColor: '#f59e0b', axisColor: '#e5e7eb', side: 'left' },
          ],
        },
        {
          xAxisKey: 'x2',
          yAxes: [
            {
              key: 'y2',
              title: '汇率相对变化 (%)',
              titleColor: '#06b6d4',
              axisColor: '#e5e7eb',
              side: 'left',
              zeroline: true,
              zerolinecolor: '#666',
              zerolinewidth: 1,
            },
          ],
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={2} />;
}
