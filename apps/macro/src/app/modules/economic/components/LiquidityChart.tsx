'use client';

/**
 * 流动性/风险 Tab — 3 个联动单轴子图（独立 Plot 实例）
 * 上：VIX
 * 中：HIBOR 隔夜
 * 下：TGA 余额（百万美元 → 千亿美元）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  type SubplotPanelSpec,
} from '@/lib/utils/plotlyTheme';
import { LinkedSubplots } from './LinkedSubplots';

interface LiquidityChartProps {
  data: EconomicDataResponse;
}

const META = {
  vix:   { label: 'VIX恐慌指数', color: '#a855f7', unit: '',         factor: 1 },
  hibor: { label: 'HIBOR隔夜',   color: '#14b8a6', unit: '%',        factor: 1 },
  tga:   { label: 'TGA余额',     color: '#f97316', unit: '千亿美元', factor: 1e-5 },
} as const;

function tracesOf(...items: Array<Data | null>): Data[] {
  return items.filter((t): t is Data => t != null);
}

export function LiquidityChart({ data }: LiquidityChartProps) {
  const subplots = useMemo<SubplotPanelSpec[]>(() => {
    const dates = data.dates ?? [];

    const scale = (raw: Array<number | null | undefined> | undefined, factor: number) =>
      (raw ?? []).map((v) => (v == null ? null : (v as number) * factor));

    return [
      {
        traces: tracesOf(
          buildLineTrace(
            { label: META.vix.label, color: META.vix.color, unit: META.vix.unit, yaxis: 'y', xaxis: 'x' },
            dates,
            scale(data.vix, META.vix.factor),
          ),
        ),
        spec: {
          xAxisKey: 'x',
          yAxes: [
            { key: 'y', title: 'VIX', titleColor: META.vix.color, axisColor: META.vix.color, side: 'left' },
          ],
        },
        emptyMessage: '暂无 VIX 数据',
      },
      {
        traces: tracesOf(
          buildLineTrace(
            { label: META.hibor.label, color: META.hibor.color, unit: META.hibor.unit, yaxis: 'y2', xaxis: 'x2', valueFormat: '.3f' },
            dates,
            scale(data.hibor, META.hibor.factor),
          ),
        ),
        spec: {
          xAxisKey: 'x2',
          yAxes: [
            { key: 'y2', title: 'HIBOR (%)', titleColor: META.hibor.color, axisColor: META.hibor.color, side: 'left' },
          ],
        },
        emptyMessage: '暂无 HIBOR 数据',
      },
      {
        traces: tracesOf(
          buildLineTrace(
            { label: META.tga.label, color: META.tga.color, unit: META.tga.unit, yaxis: 'y3', xaxis: 'x3' },
            dates,
            scale(data.tga, META.tga.factor),
          ),
        ),
        spec: {
          xAxisKey: 'x3',
          yAxes: [
            { key: 'y3', title: 'TGA (千亿美元)', titleColor: META.tga.color, axisColor: META.tga.color, side: 'left' },
          ],
        },
        emptyMessage: '暂无 TGA 数据',
      },
    ];
  }, [data]);

  return <LinkedSubplots subplots={subplots} />;
}
