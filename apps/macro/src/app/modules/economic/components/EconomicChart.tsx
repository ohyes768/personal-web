/**
 * 经济数据图表组件 — 中美利差 / 汇率
 * 上图：美债 + 中国10y（收益率 %）
 * 下图：汇率相对变化 %（tooltip 同时显示原始汇率）
 * 拆分方案：两个子图独立实例（图例各自在上方），x 轴由 LinkedSubplots 联动
 */
'use client';

import { useMemo } from 'react';
import type { ChartContext } from '@/lib/utils/chartTheme';
import type { ChartSeries } from '@/lib/utils/chartTheme';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  hasValidPoints,
  type SubplotPanelSpec,
} from '@/lib/utils/chartTheme';
import { LinkedSubplots } from './LinkedSubplots';

interface EconomicChartProps {
  onContextChange?: (context: ChartContext) => void;
  data: EconomicDataResponse;
  showAllData?: boolean;
}

function relativeChange(values: Array<number | null | undefined>): Array<number | null> {
  const base = values.find((v) => v != null && !Number.isNaN(v as number));
  if (base == null || base === 0) return values.map(() => null);
  return values.map((v) => {
    if (v == null || Number.isNaN(v as number)) return null;
    return (((v as number) - (base as number)) / (base as number)) * 100;
  });
}

export function EconomicChart({ data, onContextChange }: EconomicChartProps) {
  const subplots = useMemo<SubplotPanelSpec[]>(() => {
    const dates = data.dates ?? [];
    const us = data.us_treasuries;
    const china = data.china_bond;
    const fx = data.exchange_rates;

    const rateTraces: ChartSeries[] = [];

    const pushRate = (
      id: string,
      label: string,
      color: string,
      series: Array<number | null | undefined> | undefined,
      dash: 'solid' | 'dash' | 'dot' = 'solid',
    ) => {
      const t = buildLineTrace(
        { id, label, color, unit: '%', yaxis: 'y', xaxis: 'x', dash, valueFormat: '.3f' },
        dates,
        series ?? [],
      );
      if (t) rateTraces.push(t);
    };

    pushRate('us_3m', '美债3M', '#3b82f6', us?.['3m'], 'dot');
    pushRate('us_2y', '美债2Y', '#10b981', us?.['2y'], 'dash');
    pushRate('us_10y', '美债10Y', '#f59e0b', us?.['10y'], 'solid');
    pushRate('cn_10y', '中国10Y', '#fbbf24', china?.['10y'], 'dash');

    const fxTraces: ChartSeries[] = [];

    const pushFx = (
      id: string,
      label: string,
      color: string,
      series: Array<number | null | undefined> | undefined,
      dash: 'solid' | 'dash' | 'dot' = 'solid',
    ) => {
      const raw = series ?? [];
      if (!hasValidPoints(raw)) return;
      const rel = relativeChange(raw);
      const t = buildLineTrace(
        { id, label, color, unit: '%', transform: 'relative', yaxis: 'y2', xaxis: 'x2', dash, valueFormat: '.2f' },
        dates,
        rel,
        {
          details: [{ label: '原始值', values: raw.map((v) => v ?? null), decimals: 4 }],
        },
      );
      if (t) fxTraces.push(t);
    };

    pushFx('dxy', '美元指数', '#06b6d4', fx?.dollar_index, 'solid');
    pushFx('usd_cny', 'USD/CNY', '#ec4899', fx?.usd_cny, 'dash');
    pushFx('usd_jpy', 'USD/JPY', '#a78bfa', fx?.usd_jpy, 'dot');
    pushFx('usd_eur', 'USD/EUR', '#34d399', fx?.usd_eur, 'dash');

    return [
      {
        id: 'treasury-exchange.yields',
        traces: rateTraces,
        spec: {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '收益率 (%)', titleColor: '#f59e0b', axisColor: '#e5e7eb', side: 'left' },
          ],
        },
        emptyMessage: '暂无收益率数据',
      },
      {
        id: 'treasury-exchange.fx',
        traces: fxTraces,
        spec: {
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
        emptyMessage: '暂无汇率数据',
      },
    ];
  }, [data]);

  return <LinkedSubplots onContextChange={onContextChange} chartId="treasury-exchange" subplots={subplots} />;
}
