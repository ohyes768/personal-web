/**
 * 经济数据图表组件
 */
'use client';

import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { useDarkMode } from '@/lib/hooks/useDarkMode';
import { createTreasuryTraces, createExchangeTraces, createChartLayout, createChartConfig } from '@/lib/utils/chartConfig';

interface EconomicChartProps {
  data: EconomicDataResponse;
}

export function EconomicChart({ data }: EconomicChartProps) {
  const isDarkMode = useDarkMode();

  // 生成美债图表数据系列
  const treasuryTraces = useMemo(() => {
    return createTreasuryTraces(data.dates, data.us_treasuries);
  }, [data]);

  // 生成汇率图表数据系列
  const exchangeTraces = useMemo(() => {
    if (!data.exchange_rates) return [];
    return createExchangeTraces(data.dates, data.exchange_rates);
  }, [data]);

  // 生成图表布局
  const layout = useMemo(() => {
    return createChartLayout(isDarkMode);
  }, [isDarkMode]);

  // 生成图表配置
  const config = useMemo(() => {
    return createChartConfig();
  }, []);

  // 如果没有汇率数据，只显示美债
  const traces = exchangeTraces.length > 0
    ? [...treasuryTraces, ...exchangeTraces]
    : treasuryTraces;

  return (
    <Plot
      data={traces}
      layout={layout}
      config={config}
      style={{ width: '100%', height: '700px' }}
      className="w-full"
      useResizeHandler
    />
  );
}
