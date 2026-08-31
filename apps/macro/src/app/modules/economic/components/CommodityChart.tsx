'use client';

/**
 * 商品 Tab — 2 个联动子图（独立 Plot 实例）
 * 上图：黄金（左）+ 白银（右）
 * 下图：原油（左）+ 铜（右）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  type SubplotPanelSpec,
} from '@/lib/utils/plotlyTheme';
import { LinkedSubplots } from './LinkedSubplots';

interface CommodityChartProps {
  data: EconomicDataResponse;
}

const META = {
  gold:   { label: '黄金', color: '#eab308', unit: '元/克', dash: 'solid' as const },
  silver: { label: '白银', color: '#94a3b8', unit: '元/克', dash: 'dash' as const },
  oil:    { label: '原油', color: '#38bdf8', unit: '$/桶',  dash: 'solid' as const },
  copper: { label: '铜',   color: '#f97316', unit: '$/吨',  dash: 'dash' as const },
} as const;

function tracesOf(...items: Array<Data | null>): Data[] {
  return items.filter((t): t is Data => t != null);
}

export function CommodityChart({ data }: CommodityChartProps) {
  const subplots = useMemo<SubplotPanelSpec[]>(() => {
    const dates = data.dates ?? [];
    const commodities = data.commodities;

    const line = (
      key: keyof typeof META,
      yaxis: 'y' | 'y2' | 'y3' | 'y4',
      xaxis: 'x' | 'x2',
    ) =>
      buildLineTrace(
        {
          label: META[key].label,
          color: META[key].color,
          unit: META[key].unit,
          yaxis,
          xaxis,
          dash: META[key].dash,
        },
        dates,
        commodities?.[key] ?? [],
      );

    return [
      {
        traces: tracesOf(line('gold', 'y', 'x'), line('silver', 'y2', 'x')),
        spec: {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: '黄金 (元/克)', titleColor: META.gold.color, axisColor: META.gold.color, side: 'left' },
            { key: 'y2', title: '白银 (元/克)', titleColor: META.silver.color, axisColor: META.silver.color, side: 'right', overlaying: 'y' },
          ],
        },
        emptyMessage: '暂无贵金属数据',
      },
      {
        traces: tracesOf(line('oil', 'y3', 'x2'), line('copper', 'y4', 'x2')),
        spec: {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y3', title: '原油 ($/桶)', titleColor: META.oil.color, axisColor: META.oil.color, side: 'left' },
            { key: 'y4', title: '铜 ($/吨)', titleColor: META.copper.color, axisColor: META.copper.color, side: 'right', overlaying: 'y3' },
          ],
        },
        emptyMessage: '暂无能源/工业金属数据',
      },
    ];
  }, [data]);

  return <LinkedSubplots subplots={subplots} />;
}
