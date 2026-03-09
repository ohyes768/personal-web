/**
 * 经济数据图表组件
 */
'use client';

import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { useDarkMode } from '@/lib/hooks/useDarkMode';
import { createTreasuryTraces, createEuroBondTraces, createJapanBondTraces, createExchangeTraces, createVIXTraces, createChartLayout, createTwoChartLayout, createThreeChartLayout, createChartConfig } from '@/lib/utils/chartConfig';

interface EconomicChartProps {
  data: EconomicDataResponse;
  showAllData?: boolean; // 是否显示所有数据（美债+欧债+日债+汇率），默认只显示美债+汇率
}

export function EconomicChart({ data, showAllData = false }: EconomicChartProps) {
  const isDarkMode = useDarkMode();

  // 生成美债图表数据系列
  const treasuryTraces = useMemo(() => {
    return createTreasuryTraces(data.dates, data.us_treasuries);
  }, [data]);

  // 生成欧债图表数据系列
  const euroBondTraces = useMemo(() => {
    if (!data.eu_treasuries?.['10y'] || data.eu_treasuries['10y'].length === 0) return [];
    return createEuroBondTraces(data.dates, data.eu_treasuries);
  }, [data]);

  // 生成日债图表数据系列
  const japanBondTraces = useMemo(() => {
    if (!data.jp_treasuries?.['10y'] || data.jp_treasuries['10y'].length === 0) return [];
    return createJapanBondTraces(data.dates, data.jp_treasuries);
  }, [data]);

  // 生成汇率图表数据系列
  const exchangeTraces = useMemo(() => {
    if (!data.exchange_rates) return [];
    return createExchangeTraces(data.dates, data.exchange_rates);
  }, [data]);

  // 生成VIX图表数据系列
  const vixTraces = useMemo(() => {
    if (!data.vix || data.vix.length === 0) return [];
    return createVIXTraces(data.dates, data.vix);
  }, [data]);

  // 合并图表数据：如果 showAllData 为 true，则显示所有数据；否则只显示美债、汇率和VIX
  const traces = showAllData
    ? [
        ...treasuryTraces,
        ...euroBondTraces,
        ...japanBondTraces,
        ...exchangeTraces,
      ]
    : [
        ...treasuryTraces,
        ...exchangeTraces,
        ...vixTraces,
      ];

  // 生成图表布局
  const layout = useMemo(() => {
    if (showAllData) {
      // 显示所有数据时使用4个子图布局
      const baseLayout = createChartLayout(isDarkMode);
      return {
        ...baseLayout,
        xaxis: {
          ...baseLayout.xaxis,
          autorange: true,
        },
        xaxis2: {
          ...baseLayout.xaxis2,
          autorange: true,
        },
        xaxis3: {
          ...baseLayout.xaxis3,
          autorange: true,
        },
        xaxis4: {
          ...baseLayout.xaxis4,
          autorange: true,
        },
      };
    } else {
      // 只显示美债、汇率和VIX时使用3个子图布局
      return createThreeChartLayout(isDarkMode);
    }
  }, [isDarkMode, showAllData]);

  // 生成图表配置
  const config = useMemo(() => {
    return createChartConfig();
  }, []);

  return (
    <Plot
      data={traces}
      layout={layout}
      config={config}
      style={{ width: '100%', height: showAllData ? '1000px' : '1200px' }}
      className="w-full"
      useResizeHandler
    />
  );
}
