'use client';

/**
 * 沪深港通资金图 — 双轴
 * 左：北向成交额
 * 右：南向净流入（含 0 线）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  buildLineTrace,
  buildMultiAxisLayout,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

interface HsgtFundFlowChartProps {
  data: EconomicDataResponse;
}

export function HsgtFundFlowChart({ data }: HsgtFundFlowChartProps) {
  const { traces, layout } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces = [
      buildLineTrace(
        {
          label: '北向成交额',
          color: '#06b6d4',
          unit: '亿元',
          yaxis: 'y',
          valueFormat: ',.0f',
        },
        dates,
        data.fund_flow?.north_deal_amount ?? [],
      ),
      buildLineTrace(
        {
          label: '南向净流入',
          color: '#ec4899',
          unit: '亿元',
          yaxis: 'y2',
          dash: 'dash',
          valueFormat: ',.0f',
        },
        dates,
        data.fund_flow?.south_net_flow ?? [],
      ),
    ].filter(Boolean) as Data[];

    const layout = buildMultiAxisLayout({
      axes: [
        {
          key: 'y',
          title: '北向成交额 (亿元)',
          titleColor: '#06b6d4',
          axisColor: '#e5e7eb',
          side: 'left',
        },
        {
          key: 'y2',
          title: '南向净流入 (亿元)',
          titleColor: '#ec4899',
          axisColor: '#ec4899',
          side: 'right',
          overlaying: 'y',
          zeroline: true,
          zerolinecolor: '#666',
          zerolinewidth: 1,
        },
      ],
    });

    return { traces, layout };
  }, [data]);

  return <MacroPlot data={traces} layout={layout} subplotCount={1} emptyMessage="暂无沪深港通数据" />;
}
