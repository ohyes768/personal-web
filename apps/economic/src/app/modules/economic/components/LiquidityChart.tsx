'use client';

/**
 * 流动性/风险 Tab — Plotly 同图 3 轴叠加
 * - y（左）   ：VIX 恐慌指数        ~10-30（极端 80+）
 * - y2（左内）：HIBOR 隔夜拆息       ~0-10%
 * - y3（右）  ：TGA 账户余额         ~3-9 千亿美元（原始百万美元 ÷ 1e5）
 *
 * 每个指标独立 scale，避免数值差异太大导致曲线被压扁
 * - 缺失段 Plotly connectgaps=false 自动断开
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  buildMultiAxisLayout,
  type AxisSpec,
} from '@/lib/utils/plotlyTheme';

interface LiquidityChartProps {
  data: EconomicDataResponse;
}

const LIQUIDITY_META = {
  vix:   { label: 'VIX恐慌指数', color: '#a855f7', axis: 'y',  unit: '',         displayFactor: 1,     side: 'left'  as const },
  hibor: { label: 'HIBOR隔夜',   color: '#14b8a6', axis: 'y2', unit: '%',        displayFactor: 1,     side: 'left'  as const },
  tga:   { label: 'TGA余额',     color: '#f97316', axis: 'y3', unit: '千亿美元', displayFactor: 1e-5, side: 'right' as const },
} as const;

type LiquidityKey = keyof typeof LIQUIDITY_META;

/** y 轴定义：title/titleColor/axisColor/side/overlaying/position。 */
const AXES: AxisSpec[] = [
  { key: 'y',  title: 'VIX 恐慌指数',          titleColor: '#a855f7', axisColor: '#e5e7eb', side: 'left' },
  { key: 'y2', title: 'HIBOR 隔夜 (%)',         titleColor: '#14b8a6', axisColor: '#14b8a6', side: 'left',  overlaying: 'y', position: 0.06 },
  { key: 'y3', title: 'TGA 余额 (千亿美元)',    titleColor: '#f97316', axisColor: '#f97316', side: 'right', overlaying: 'y' },
];

export function LiquidityChart({ data }: LiquidityChartProps) {
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces: Array<Record<string, unknown>> = (
      Object.keys(LIQUIDITY_META) as LiquidityKey[]
    ).map((k) => {
      const meta = LIQUIDITY_META[k];
      const raw = data[k] ?? [];
      // 应用 displayFactor 转换单位（TGA: 百万美元 → 千亿美元）
      const y = raw.map((v) => (v == null ? null : (v as number) * meta.displayFactor));
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
          `数值: %{y:.2f} ${meta.unit}` +
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