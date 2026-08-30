'use client';

/**
 * 商品 Tab — 2 个联动子图
 * 上图：黄金（左）+ 白银（右）
 * 下图：原油（左）+ 铜（右）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildLinkedSubplotLayout,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface CommodityChartProps {
  data: EconomicDataResponse;
}

const META = {
  gold:   { label: '黄金', color: '#eab308', unit: '元/克', dash: 'solid' as const },
  silver: { label: '白银', color: '#94a3b8', unit: '元/克', dash: 'dash' as const },
  oil:    { label: '原油', color: '#38bdf8', unit: '$/桶',  dash: 'solid' as const },
  copper: { label: '铜',   color: '#f97316', unit: '$/吨',  dash: 'dash' as const },
} as const;

export function CommodityChart({ data }: CommodityChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];
    const commodities = data.commodities;

    const traces = [
      buildLineTrace(
        { label: META.gold.label, color: META.gold.color, unit: META.gold.unit, yaxis: 'y', xaxis: 'x', dash: META.gold.dash },
        dates,
        commodities?.gold ?? [],
      ),
      buildLineTrace(
        { label: META.silver.label, color: META.silver.color, unit: META.silver.unit, yaxis: 'y2', xaxis: 'x', dash: META.silver.dash },
        dates,
        commodities?.silver ?? [],
      ),
      buildLineTrace(
        { label: META.oil.label, color: META.oil.color, unit: META.oil.unit, yaxis: 'y3', xaxis: 'x2', dash: META.oil.dash },
        dates,
        commodities?.oil ?? [],
      ),
      buildLineTrace(
        { label: META.copper.label, color: META.copper.color, unit: META.copper.unit, yaxis: 'y4', xaxis: 'x2', dash: META.copper.dash },
        dates,
        commodities?.copper ?? [],
      ),
    ].filter(Boolean) as Data[];

    const layout = buildLinkedSubplotLayout({
      subplots: [
        {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '黄金 (元/克)', titleColor: META.gold.color, axisColor: META.gold.color, side: 'left' },
            { key: 'y2', title: '白银 (元/克)', titleColor: META.silver.color, axisColor: META.silver.color, side: 'right', overlaying: 'y' },
          ],
        },
        {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y3', title: '原油 ($/桶)', titleColor: META.oil.color, axisColor: META.oil.color, side: 'left' },
            { key: 'y4', title: '铜 ($/吨)', titleColor: META.copper.color, axisColor: META.copper.color, side: 'right', overlaying: 'y3' },
          ],
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={2} />;
}
