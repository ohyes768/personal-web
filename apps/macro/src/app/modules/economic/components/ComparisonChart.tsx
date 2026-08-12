'use client';

/**
 * 对比模块 — Plotly 多模式图表
 *
 * 四种模式（用户手动切换，不做自动判定）：
 * 1. minMax:               满幅百分位（每条线 min=0, max=100，Y 轴留 10% 上下边距 = 占 80%）
 * 2. normalize:            起点归一 100，单 Y 轴（适合同质指标看相对涨跌）
 * 3. dualAxis:             真实值，按 unit 分配左右轴（看绝对水平）
 * 4. dualAxisWithCorrelation: 双轴 + 下方 30 日滚动 Pearson 相关性子图（仅 2 指标时）
 */
import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { INDICATORS } from '@/lib/modules/comparison/indicators';
import { extractSeries, normalize, minMaxNormalize } from '@/lib/modules/comparison/normalize';
import { rollingCorrelation } from '@/lib/modules/comparison/stats';
import { buildDualAxisAssignment } from '@/lib/modules/comparison/viewMode';
import type { IndicatorId, ViewMode } from '@/lib/modules/comparison/types';
import {
  BASE_PLOT_CONFIG,
  PLOTLY_DARK,
  buildMultiAxisLayout,
} from '@/lib/utils/plotlyTheme';
import { usePlotlyAutoResize } from '@/lib/hooks/usePlotlyAutoResize';

interface ComparisonChartProps {
  selectedIds: IndicatorId[];
  data: EconomicDataResponse;
  viewMode: ViewMode;
}

const CORR_WINDOW = 30;
const CORR_MIN_SAMPLES = 10;

export function ComparisonChart({ selectedIds, data, viewMode }: ComparisonChartProps) {
  const containerRef = usePlotlyAutoResize<HTMLDivElement>();
  const { traces, layout, config } = useMemo(() => {
    const dates = data.dates;
    const { traces, layout } = buildByMode(selectedIds, data, viewMode);
    return { traces, layout, config: BASE_PLOT_CONFIG };
  }, [selectedIds, data, viewMode]);

  if (selectedIds.length === 0) {
    return (
      <div ref={containerRef} style={{ width: '100%' }}>
        <div className="bg-gray-900 rounded-lg p-12 border border-gray-800 text-center">
          <p className="text-gray-400 text-lg">请至少选择 1 个指标开始对比</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <Plot
        data={traces as never}
        layout={layout}
        config={config}
        style={{ width: '100%', height: viewMode === 'dualAxisWithCorrelation' ? '900px' : '700px' }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}

/**
 * 按模式构造 traces + layout
 * 相关性模式在指标数 ≠ 2 时自动降级为纯双轴（保留模式状态，避免空子图）
 */
function buildByMode(
  ids: IndicatorId[],
  data: EconomicDataResponse,
  mode: ViewMode,
): { traces: Array<Record<string, unknown>>; layout: Record<string, unknown> } {
  if (mode === 'minMax') return buildMinMax(ids, data);
  if (mode === 'normalize') return buildNormalize(ids, data);
  if (mode === 'dualAxis') return buildDualAxis(ids, data);
  if (mode === 'dualAxisWithCorrelation' && ids.length === 2) {
    return buildDualAxisWithCorrelation(ids, data);
  }
  return buildDualAxis(ids, data);
}

/** 模式 1：满幅百分位（min-max 归一化到 [0, 100]，Y 轴 range [-12.5, 112.5] 让曲线占 80% 上下高度） */
function buildMinMax(ids: IndicatorId[], data: EconomicDataResponse) {
  const dates = data.dates;
  const traces = ids.map((id) => {
    const meta = INDICATORS[id];
    const raw = extractSeries(data, id);
    const norm = minMaxNormalize(raw);
    return {
      type: 'scatter',
      mode: 'lines',
      name: meta.label,
      x: dates,
      y: norm,
      customdata: raw,
      line: { color: meta.color, width: 2 },
      hovertemplate:
        `<b>${meta.label}</b><br>` +
        `日期: %{x}<br>` +
        `原始值: %{customdata}${meta.unit ? ' ' + meta.unit : ''}<br>` +
        `区间百分位: %{y:.1f}%` +
        `<extra></extra>`,
      connectgaps: false,
    };
  });

  const layout = buildMultiAxisLayout({
    axes: [
      {
        key: 'y',
        title: '区间百分位（0% = 期间最低，100% = 期间最高）',
        axisColor: '#e5e7eb',
        side: 'left',
      },
    ],
    legendX: 1.02,
    margin: { l: 70, r: 180 },
  });

  // Y 轴 range 设 [-12.5, 112.5]：曲线 [0, 100] 占 100/125 = 80% 画布高度（上下各留 10%）
  (layout as Record<string, unknown>).yaxis = {
    ...((layout as Record<string, unknown>).yaxis as Record<string, unknown>),
    range: [-12.5, 112.5],
    zeroline: true,
    zerolinecolor: '#666',
    zerolinewidth: 1,
  };

  return { traces, layout: layout as Record<string, unknown> };
}

/** 模式 1：归一化（原行为） */
function buildNormalize(ids: IndicatorId[], data: EconomicDataResponse) {
  const dates = data.dates;
  const traces = ids.map((id) => {
    const meta = INDICATORS[id];
    const raw = extractSeries(data, id);
    const norm = normalize(raw);
    return {
      type: 'scatter',
      mode: 'lines',
      name: meta.label,
      x: dates,
      y: norm,
      customdata: raw,
      line: { color: meta.color, width: 2 },
      hovertemplate:
        `<b>${meta.label}</b><br>` +
        `日期: %{x}<br>` +
        `原始值: %{customdata}${meta.unit ? ' ' + meta.unit : ''}<br>` +
        `归一化: %{y:.2f}<br>` +
        `涨跌: %{y - 100:+.2f}%` +
        `<extra></extra>`,
      connectgaps: false,
    };
  });

  const layout = buildMultiAxisLayout({
    axes: [
      {
        key: 'y',
        title: '归一化值（起点 = 100）',
        axisColor: '#e5e7eb',
        side: 'left',
        zeroline: true,
        zerolinecolor: '#666',
        zerolinewidth: 1,
      },
    ],
    legendX: 1.02,
    margin: { l: 70, r: 180 },
  });

  return { traces, layout: layout as Record<string, unknown> };
}

/** 模式 2：双轴真实值 */
function buildDualAxis(ids: IndicatorId[], data: EconomicDataResponse) {
  const dates = data.dates;
  const assignment = buildDualAxisAssignment(ids);

  const traces = ids.map((id) => {
    const meta = INDICATORS[id];
    const raw = extractSeries(data, id);
    const axisKey = assignment.axisByUnit.get(meta.unit || '数值') || 'y';
    return {
      type: 'scatter',
      mode: 'lines',
      name: meta.label,
      x: dates,
      y: raw,
      yaxis: axisKey,
      line: { color: meta.color, width: 2 },
      hovertemplate:
        `<b>${meta.label}</b><br>` +
        `日期: %{x}<br>` +
        `数值: %{y}${meta.unit ? ' ' + meta.unit : ''}` +
        `<extra></extra>`,
      connectgaps: false,
    };
  });

  const layout = buildMultiAxisLayout({
    axes: assignment.axes,
    legendX: 1.02,
    margin: { l: 70, r: 180 },
  });

  return { traces, layout: layout as Record<string, unknown> };
}

/** 模式 3：双轴真实值 + 下方滚动相关性子图 */
function buildDualAxisWithCorrelation(ids: IndicatorId[], data: EconomicDataResponse) {
  const dates = data.dates;
  const assignment = buildDualAxisAssignment(ids);

  // 上图：双轴折线
  const upperTraces = ids.map((id) => {
    const meta = INDICATORS[id];
    const raw = extractSeries(data, id);
    const axisKey = assignment.axisByUnit.get(meta.unit || '数值') || 'y';
    return {
      type: 'scatter',
      mode: 'lines',
      name: meta.label,
      x: dates,
      y: raw,
      yaxis: axisKey,
      line: { color: meta.color, width: 2 },
      hovertemplate:
        `<b>${meta.label}</b><br>` +
        `日期: %{x}<br>` +
        `数值: %{y}${meta.unit ? ' ' + meta.unit : ''}` +
        `<extra></extra>`,
      connectgaps: false,
    };
  });

  // 下图：滚动相关性（仅当恰好 2 个指标时）
  let corrTrace: Record<string, unknown> | null = null;
  let corrSubtitle = '';
  if (ids.length === 2) {
    const [a, b] = ids;
    const xs = extractSeries(data, a);
    const ys = extractSeries(data, b);
    const corr = rollingCorrelation(xs, ys, CORR_WINDOW, CORR_MIN_SAMPLES);
    const validCount = corr.filter((v) => v != null).length;
    corrSubtitle = `${INDICATORS[a].label} × ${INDICATORS[b].label}（${validCount} 个有效窗口）`;
    corrTrace = {
      type: 'scatter',
      mode: 'lines',
      name: '滚动相关性',
      x: dates,
      y: corr,
      xaxis: 'x2',
      yaxis: 'y3',
      line: { color: '#fbbf24', width: 2 },
      hovertemplate:
        `<b>滚动相关性</b><br>` +
        `日期: %{x}<br>` +
        `r: %{y:.3f}` +
        `<extra></extra>`,
      connectgaps: false,
    };
  }

  // 手构造 layout：双轴 + subplot，不走 buildMultiAxisLayout（它不支持 domain + subplot）
  const mainAxisDef = assignment.axes.find((a) => a.key === 'y');
  const rightAxisDef = assignment.axes.find((a) => a.key === 'y2');

  const layout: Record<string, unknown> = {
    xaxis: {
      domain: [0, 1],
      title: '',
      showgrid: true,
      gridcolor: PLOTLY_DARK.gridColor,
      color: PLOTLY_DARK.fontColor,
      anchor: 'y',
    },
    yaxis: {
      domain: [0.45, 1.0],
      title: mainAxisDef?.title || '',
      titlefont: mainAxisDef?.titleColor ? { color: mainAxisDef.titleColor } : undefined,
      side: 'left',
      showgrid: true,
      gridcolor: PLOTLY_DARK.gridColor,
      color: mainAxisDef?.axisColor || PLOTLY_DARK.fontColor,
    },
    ...(rightAxisDef
      ? {
          yaxis2: {
            title: rightAxisDef.title,
            titlefont: rightAxisDef.titleColor ? { color: rightAxisDef.titleColor } : undefined,
            side: 'right',
            overlaying: 'y',
            anchor: 'x',
            color: rightAxisDef.axisColor,
          },
        }
      : {}),
    xaxis2: {
      domain: [0, 1],
      title: '日期',
      showgrid: true,
      gridcolor: PLOTLY_DARK.gridColor,
      color: PLOTLY_DARK.fontColor,
      anchor: 'y3',
    },
    yaxis3: {
      domain: [0, 0.35],
      title: {
        text: `30 日滚动相关性 · ${corrSubtitle}`,
        font: { color: PLOTLY_DARK.fontColor, size: 11 },
      },
      range: [-1.05, 1.05],
      showgrid: true,
      gridcolor: PLOTLY_DARK.gridColor,
      color: PLOTLY_DARK.fontColor,
      zeroline: true,
      zerolinecolor: '#666',
      zerolinewidth: 1,
    },
    shapes: [
      // 0 基线（yaxis3 zeroline 已画）
      { type: 'line', xref: 'paper', yref: 'y3', x0: 0, x1: 1, y0: 0.7, y1: 0.7, line: { color: '#ef4444', width: 1, dash: 'dot' } },
      { type: 'line', xref: 'paper', yref: 'y3', x0: 0, x1: 1, y0: -0.7, y1: -0.7, line: { color: '#ef4444', width: 1, dash: 'dot' } },
    ],
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
    margin: { l: 70, r: 180, t: 30, b: 60 },
  };

  const traces = corrTrace ? [...upperTraces, corrTrace] : upperTraces;
  return { traces, layout };
}
