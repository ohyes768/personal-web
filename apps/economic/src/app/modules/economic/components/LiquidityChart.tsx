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

interface LiquidityChartProps {
  data: EconomicDataResponse;
}

const LIQUIDITY_META = {
  vix:   { label: 'VIX恐慌指数', color: '#a855f7', axis: 'y',  unit: '',         displayFactor: 1,     side: 'left'  as const },
  hibor: { label: 'HIBOR隔夜',   color: '#14b8a6', axis: 'y2', unit: '%',        displayFactor: 1,     side: 'left'  as const },
  tga:   { label: 'TGA余额',     color: '#f97316', axis: 'y3', unit: '千亿美元', displayFactor: 1e-5, side: 'right' as const },
} as const;

type LiquidityKey = keyof typeof LIQUIDITY_META;

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

    const layout = {
      xaxis: {
        title: '日期',
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      // VIX — 主左轴
      yaxis: {
        title: { text: 'VIX 恐慌指数', font: { color: '#a855f7' } },
        side: 'left' as const,
        showgrid: true,
        gridcolor: '#333',
        color: '#e5e7eb',
      },
      // HIBOR — 左轴次轴（overlay 在 y 上）
      yaxis2: {
        title: { text: 'HIBOR 隔夜 (%)', font: { color: '#14b8a6' } },
        overlaying: 'y' as const,
        side: 'left' as const,
        position: 0.06,
        showgrid: false,
        color: '#14b8a6',
      },
      // TGA — 右轴
      yaxis3: {
        title: { text: 'TGA 余额 (千亿美元)', font: { color: '#f97316' } },
        overlaying: 'y' as const,
        side: 'right' as const,
        showgrid: false,
        color: '#f97316',
      },
      hovermode: 'x unified' as const,
      paper_bgcolor: '#1a1a1a',
      plot_bgcolor: '#1a1a1a',
      font: { color: '#e5e7eb' },
      showlegend: true,
      legend: {
        orientation: 'v' as const,
        y: 0.5,
        x: 1.02,
        xanchor: 'left' as const,
        yanchor: 'middle' as const,
      },
      margin: { l: 80, r: 200, t: 40, b: 60 },
    };

    const config = {
      responsive: true,
      displayModeBar: true,
      displaylogo: false,
      modeBarButtonsToRemove: [
        'lasso2d',
        'select2d',
        'hoverClosestCartesian',
        'hoverCompareCartesian',
        'zoom2d',
        'pan2d',
      ],
      scrollZoom: false,
      doubleClick: 'reset' as const,
    };

    return { traces, layout, config };
  }, [data]);

  return (
    <Plot
      data={traces as never}
      layout={layout as never}
      config={config as never}
      style={{ width: '100%', height: '700px' }}
      className="w-full"
      useResizeHandler
    />
  );
}