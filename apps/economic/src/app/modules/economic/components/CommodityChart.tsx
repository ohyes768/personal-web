'use client';

/**
 * 商品 Tab — Plotly 同图 4 轴叠加
 * - y（左）   ：黄金（元/克）  ~900
 * - y2（左内）：白银（元/克）  ~7
 * - y3（右）  ：原油（$/桶）   ~80
 * - y4（右）  ：铜（$/吨）    ~13000
 *
 * 每个商品独立 scale，避免数值差异太大导致曲线被压扁
 * - 历史 silver 缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  buildMultiAxisLayout,
  type AxisSpec,
} from '@/lib/utils/plotlyTheme';

interface CommodityChartProps {
  data: EconomicDataResponse;
}

const COMMODITY_META = {
  gold:   { label: '黄金', color: '#eab308', axis: 'y',  unit: '元/克', side: 'left'  as const },
  silver: { label: '白银', color: '#94a3b8', axis: 'y2', unit: '元/克', side: 'left'  as const },
  oil:    { label: '原油', color: '#1e293b', axis: 'y3', unit: '$/桶',  side: 'right' as const },
  copper: { label: '铜',   color: '#b45309', axis: 'y4', unit: '$/吨',  side: 'right' as const },
} as const;

type CommodityKey = keyof typeof COMMODITY_META;

/** y 轴定义：title/titleColor/axisColor/side/overlaying/position。 */
const AXES: AxisSpec[] = [
  { key: 'y',  title: '黄金 (元/克)', titleColor: '#eab308', axisColor: '#e5e7eb', side: 'left' },
  { key: 'y2', title: '白银 (元/克)', titleColor: '#94a3b8', axisColor: '#94a3b8', side: 'left',  overlaying: 'y', position: 0.08 },
  { key: 'y3', title: '原油 ($/桶)',  titleColor: '#1e293b', axisColor: '#e5e7eb', side: 'right', overlaying: 'y' },
  { key: 'y4', title: '铜 ($/吨)',    titleColor: '#b45309', axisColor: '#b45309', side: 'right', overlaying: 'y', position: 0.92 },
];

export function CommodityChart({ data }: CommodityChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];
    const commodities = data.commodities;

    const traces: Array<Record<string, unknown>> = (
      Object.keys(COMMODITY_META) as CommodityKey[]
    ).map((k) => {
      const meta = COMMODITY_META[k];
      const y = commodities?.[k] ?? [];
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
          `价格: %{y:.2f} ${meta.unit}` +
          `<extra></extra>`,
        connectgaps: false,
      };
    });

    const layout = buildMultiAxisLayout({ axes: AXES, legendX: 1.02 });
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