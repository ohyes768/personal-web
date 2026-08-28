'use client';

/**
 * 利率利差 Tab — Plotly 2 个 subchart 拼出
 *
 * 上图（短端利率 + 利差）：
 *   y（左）  ：DR007 + SOFR + 美债 3M   利率水平（~1.5-5%）
 *   y2（左内）：TED 利差                  信用利差（~0-1%）
 *
 * 下图（中长端）：
 *   y3（右）  ：中国 10y                中国利率水平（~1.5-3%）
 *   y4（右内）：中国 10年-2年             期限利差（~0-1%）
 *
 * 两个 subchart 共享 x 轴（matches 实现联动缩放），每个 subplot 内部独立 scale，
 * 避免 SOFR（4-5%）和 TED（0-1%）量级差 50 倍被压扁。
 * 缺失段 Plotly connectgaps=false 自动断开。
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { Layout, Config, Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import {
  BASE_PLOT_CONFIG,
  PLOTLY_DARK,
} from '@/lib/utils/plotlyTheme';
import { usePlotlyAutoResize } from '@/lib/hooks/usePlotlyAutoResize';

interface RatesChartProps {
  data: EconomicDataResponse;
}

type NestedKey = [keyof EconomicDataResponse, string];
type FlatKey = keyof EconomicDataResponse;

interface TraceMeta {
  label: string;
  color: string;
  yaxis: 'y' | 'y2' | 'y3' | 'y4';
  unit: string;
  dataKey: NestedKey | FlatKey;
}

const RATES_META: Record<string, TraceMeta> = {
  // 上图（短端）
  dr007:     { label: 'DR007',          color: '#dc2626', yaxis: 'y',  unit: '%', dataKey: 'dr007' },
  sofr:      { label: 'SOFR',          color: '#f472b6', yaxis: 'y',  unit: '%', dataKey: ['ted_spread', 'sofr'] },
  us_3m:     { label: '美债3M',         color: '#3b82f6', yaxis: 'y',  unit: '%', dataKey: ['us_treasuries', '3m'] },
  ted_spread:{ label: 'TED利差',        color: '#ec4899', yaxis: 'y2', unit: '%', dataKey: ['ted_spread', 'ted_spread'] },
  // 下图（中长端）
  cn_10y:    { label: '中国10y',        color: '#f87171', yaxis: 'y3', unit: '%', dataKey: ['china_bond', '10y'] },
  cn_10y_2y: { label: '中国10年-2年',   color: '#fb7185', yaxis: 'y4', unit: '%', dataKey: ['china_bond', 'spread_10y_2y'] },
};

// 上下图分组的轴 + 标题常量
interface AxisDef {
  key: 'y' | 'y2' | 'y3' | 'y4';
  title: string;
  titleColor: string;
  axisColor: string;
  side: 'left' | 'right';
  overlaying?: string;
  position?: number;
}

const UPPER_AXES: AxisDef[] = [
  { key: 'y',  title: '短端利率 (DR007/SOFR/美债3M, %)', titleColor: '#dc2626', axisColor: '#e5e7eb', side: 'left' },
  { key: 'y2', title: 'TED 利差 (%)',                    titleColor: '#ec4899', axisColor: '#ec4899', side: 'left', overlaying: 'y', position: 0.06 },
];

const LOWER_AXES: AxisDef[] = [
  { key: 'y3', title: '中国 10y (%)',                titleColor: '#f87171', axisColor: '#f87171', side: 'right' },
  { key: 'y4', title: '中国 10年-2年 (%)',           titleColor: '#fb7185', axisColor: '#fb7185', side: 'right', overlaying: 'y3', position: 0.94 },
];

/** 取 series：dataKey 为 FlatKey（如 'dr007'）→ 取顶层数组；为 NestedKey（如 ['china_bond', '10y']）→ 取嵌套字段 */
function pickSeries(data: EconomicDataResponse, dataKey: NestedKey | FlatKey): (number | null)[] {
  if (typeof dataKey === 'string') {
    // flat key：data[key] 必须是数组（如 dr007、hibor）
    const v = data[dataKey] as unknown;
    return Array.isArray(v) ? (v as (number | null)[]) : [];
  }
  const [k1, k2] = dataKey;
  const v1 = data[k1] as unknown;
  if (v1 && typeof v1 === 'object' && !Array.isArray(v1)) {
    const v2 = (v1 as Record<string, unknown>)[k2];
    return Array.isArray(v2) ? (v2 as (number | null)[]) : [];
  }
  return [];
}

function buildAxisDef(axis: AxisDef, isMain: boolean) {
  const titleObj = { text: axis.title, font: { color: axis.titleColor } };
  return {
    title: titleObj,
    side: axis.side,
    overlaying: axis.overlaying,
    position: axis.position,
    showgrid: isMain,
    gridcolor: PLOTLY_DARK.gridColor,
    color: axis.axisColor,
  };
}

export function RatesChart({ data }: RatesChartProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates ?? [];

    const traces: Data[] = (Object.keys(RATES_META) as Array<keyof typeof RATES_META>).map((k) => {
      const meta = RATES_META[k];
      const y = pickSeries(data, meta.dataKey);
      return {
        type: 'scatter',
        mode: 'lines',
        name: meta.label,
        x: dates,
        y,
        yaxis: meta.yaxis,
        line: { color: meta.color, width: 2 },
        hovertemplate:
          `<b>${meta.label}</b><br>` +
          `日期: %{x}<br>` +
          `数值: %{y:.3f} ${meta.unit}` +
          `<extra></extra>`,
        connectgaps: false,
      } as Data;
    });

    // 上图（短端）：y / y2
    const upperY = buildAxisDef(UPPER_AXES[0], true);
    const upperY2 = buildAxisDef(UPPER_AXES[1], false);
    // 下图（中长端）：y3 / y4，overlaying:'y3'
    const lowerY3 = buildAxisDef(LOWER_AXES[0], true);
    const lowerY4 = buildAxisDef(LOWER_AXES[1], false);

    const layout: Partial<Layout> = {
      grid: { rows: 2, columns: 1, pattern: 'independent', roworder: 'top to bottom' },
      // 上图 x 轴（domain 控制上下图占比，row 1 = 上面 subplot）
      xaxis: {
        title: '日期（短端）',
        showgrid: true,
        gridcolor: PLOTLY_DARK.gridColor,
        color: PLOTLY_DARK.fontColor,
        anchor: 'y2',
        domain: [0, 1],
      },
      // 下图 x 轴
      xaxis2: {
        title: '日期（中长端）',
        showgrid: true,
        gridcolor: PLOTLY_DARK.gridColor,
        color: PLOTLY_DARK.fontColor,
        anchor: 'y4',
        domain: [0, 1],
      },
      yaxis: upperY,
      yaxis2: upperY2,
      yaxis3: lowerY3,
      yaxis4: lowerY4,
      hovermode: 'x unified',
      paper_bgcolor: PLOTLY_DARK.paper_bgcolor,
      plot_bgcolor: PLOTLY_DARK.plot_bgcolor,
      font: { color: PLOTLY_DARK.fontColor },
      showlegend: true,
      legend: {
        orientation: 'v',
        y: 0.5,
        x: 1.02,
        xanchor: 'left',
        yanchor: 'middle',
      },
      margin: { l: 80, r: 220, t: 30, b: 50 },
      height: 900,
    } as Partial<Layout>;

    const config: Partial<Config> = BASE_PLOT_CONFIG;

    return { traces, layout, config };
  }, [data]);

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <Plot
        data={traces}
        layout={layout}
        config={config}
        style={{ width: '100%', height: '900px' }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}