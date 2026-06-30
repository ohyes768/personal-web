'use client';

/**
 * 利率利差 Tab — Plotly 同图 4 轴叠加
 * - y（左）  ：SOFR + 美债 3M  利率水平（~4-5%）
 * - y2（左内）：TED 利差            信用利差（~0-1%）
 * - y3（右）  ：中国 10y          中国利率水平（~1.5-3%）
 * - y4（右内）：中国 10年-2年       期限利差（~0-1%）
 *
 * 每个指标独立 scale，避免 SOFR（4-5%）和 TED（0-1%）量级差 50 倍导致被压扁
 * 缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  buildMultiAxisLayout,
  type AxisSpec,
} from '@/lib/utils/plotlyTheme';

interface RatesChartProps {
  data: EconomicDataResponse;
}

type NestedKey = [keyof EconomicDataResponse, string];

const RATES_META = {
  sofr:       { label: 'SOFR',          color: '#f472b6', axis: 'y',  unit: '%', dataKey: ['ted_spread', 'sofr']       as NestedKey },
  us_3m:      { label: '美债3M',         color: '#3b82f6', axis: 'y',  unit: '%', dataKey: ['us_treasuries', '3m']       as NestedKey },
  ted_spread: { label: 'TED利差',        color: '#ec4899', axis: 'y2', unit: '%', dataKey: ['ted_spread', 'ted_spread']  as NestedKey },
  cn_10y:     { label: '中国10y',        color: '#f87171', axis: 'y3', unit: '%', dataKey: ['china_bond', '10y']         as NestedKey },
  cn_10y_2y:  { label: '中国10年-2年',   color: '#fb7185', axis: 'y4', unit: '%', dataKey: ['china_bond', 'spread_10y_2y'] as NestedKey },
} as const;

type RatesKey = keyof typeof RATES_META;

/** y 轴定义：title/titleColor/axisColor/side/overlaying/position。 */
const AXES: AxisSpec[] = [
  { key: 'y',  title: '利率水平 (SOFR / 美债3M, %)', titleColor: '#f472b6', axisColor: '#e5e7eb', side: 'left' },
  { key: 'y2', title: 'TED 利差 (%)',                titleColor: '#ec4899', axisColor: '#ec4899', side: 'left',  overlaying: 'y', position: 0.06 },
  { key: 'y3', title: '中国 10y (%)',                titleColor: '#f87171', axisColor: '#f87171', side: 'right', overlaying: 'y' },
  { key: 'y4', title: '中国 10年-2年 (%)',           titleColor: '#fb7185', axisColor: '#fb7185', side: 'right', overlaying: 'y', position: 0.94 },
];

/** 嵌套取值：data[key1] 是对象时取 data[key1][key2]，否则取 data[key1] */
function pickSeries(data: EconomicDataResponse, [k1, k2]: NestedKey): (number | null)[] {
  const v1 = data[k1] as unknown;
  if (v1 && typeof v1 === 'object' && !Array.isArray(v1)) {
    const v2 = (v1 as Record<string, unknown>)[k2];
    return Array.isArray(v2) ? (v2 as (number | null)[]) : [];
  }
  return [];
}

export function RatesChart({ data }: RatesChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces: Array<Record<string, unknown>> = (
      Object.keys(RATES_META) as RatesKey[]
    ).map((k) => {
      const meta = RATES_META[k];
      const y = pickSeries(data, meta.dataKey);
      return {
        type: 'scatter',
        mode: 'lines',
        name: meta.label,
        x: dates,
        y,
        yaxis: meta.axis,
        line: { color: meta.color, width: 2 },
        hovertemplate:
          `<b>${meta.label}</b><br>` +
          `日期: %{x}<br>` +
          `数值: %{y:.3f} ${meta.unit}` +
          `<extra></extra>`,
        connectgaps: false,
      };
    });

    const layout = buildMultiAxisLayout({ axes: AXES, legendX: 1.06, margin: { r: 220 } });
    const config = BASE_PLOT_CONFIG;

    return { traces, layout, config };
  }, [data]);

  return (
    <Plot
      data={traces as never}
      layout={layout}
      config={config}
      style={{ width: '100%', height: '700px' }}
      className="w-full"
      useResizeHandler
    />
  );
}