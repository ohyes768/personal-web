/**
 * 德债日债图表组件
 */
'use client';

import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { useDarkMode } from '@/lib/hooks/useDarkMode';
import { createBondChartLayout, createBondChartConfig } from '@/lib/utils/chartConfig';

interface BondChartProps {
  data: EconomicDataResponse;
}

export function BondChart({ data }: BondChartProps) {
  const isDarkMode = useDarkMode();

  // 生成德债图表数据系列
  const germanyTraces = useMemo(() => {
    if (!data.eu_treasuries) return [];
    return [
      {
        x: data.dates,
        y: data.eu_treasuries['10y'],
        name: '德债 10 年期',
        mode: 'lines',
        line: { color: '#EF4444', width: 2 },
        xaxis: 'x',
        yaxis: 'y',
      },
      {
        x: data.dates,
        y: data.eu_treasuries['2y'],
        name: '德债 2 年期',
        mode: 'lines',
        line: { color: '#F97316', width: 2 },
        xaxis: 'x',
        yaxis: 'y',
      },
      {
        x: data.dates,
        y: data.eu_treasuries['3m'],
        name: '德债 3 个月期',
        mode: 'lines',
        line: { color: '#3B82F6', width: 2 },
        xaxis: 'x',
        yaxis: 'y',
      },
    ];
  }, [data]);

  // 生成日债图表数据系列
  const japanTraces = useMemo(() => {
    if (!data.jp_treasuries) return [];
    return [
      {
        x: data.dates,
        y: data.jp_treasuries['10y'],
        name: '日债 10 年期',
        mode: 'lines',
        line: { color: '#8B5CF6', width: 2 },
        xaxis: 'x',
        yaxis: 'y',
      },
    ];
  }, [data]);

  // 合并图表数据：德债10年、德债2年、德债3个月期、日债10年
  const traces = [
    ...germanyTraces,
    ...japanTraces,
  ];

  // 生成图表布局（1个子图）
  const layout = useMemo(() => {
    return createBondChartLayout(isDarkMode);
  }, [isDarkMode]);

  // 生成图表配置
  const config = useMemo(() => {
    return createBondChartConfig();
  }, []);

  return (
    <Plot
      data={traces}
      layout={layout}
      config={config}
      style={{ width: '100%', height: '800px' }}
      className="w-full"
      useResizeHandler
    />
  );
}