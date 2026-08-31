'use client';

/**
 * 对比模块 — Plotly 多模式图表
 *
 * 1. minMax: 满幅百分位
 * 2. normalize: 起点归一 100（涨跌预计算到 customdata）
 * 3. dualAxis: 真实值；1-2 种单位双轴，3+ 种单位按单位拆子图
 * 4. dualAxisWithCorrelation: 双轴 + 下方滚动相关性（仅 2 指标）
 */
import { useMemo } from 'react';
import type { Data } from 'plotly.js';
import type { EconomicDataResponse } from '@/lib/types/economic';
import { INDICATORS } from '@/lib/modules/comparison/indicators';
import { extractSeries, normalize, minMaxNormalize } from '@/lib/modules/comparison/normalize';
import { rollingCorrelation } from '@/lib/modules/comparison/stats';
import { buildDualAxisAssignment } from '@/lib/modules/comparison/viewMode';
import type { IndicatorId, ViewMode } from '@/lib/modules/comparison/types';
import {
  buildMultiAxisLayout,
  buildLineTrace,
  chartHeightForSubplots,
  type AxisKey,
  type SubplotPanelSpec,
  type XAxisKey,
} from '@/lib/utils/plotlyTheme';
import { LinkedSubplots } from './LinkedSubplots';
import { MacroPlot } from './MacroPlot';

interface ComparisonChartProps {
  selectedIds: IndicatorId[];
  data: EconomicDataResponse;
  viewMode: ViewMode;
}

const CORR_WINDOW = 30;
const CORR_MIN_SAMPLES = 10;
const DASHES = ['solid', 'dash', 'dot', 'dashdot'] as const;

type BuiltChart =
  | {
      kind: 'single';
      traces: Data[];
      layout: Record<string, unknown>;
      subplotCount: number;
    }
  | {
      kind: 'linked';
      subplots: SubplotPanelSpec[];
    };

export function ComparisonChart({ selectedIds, data, viewMode }: ComparisonChartProps) {
  const chart = useMemo(
    () => buildByMode(selectedIds, data, viewMode),
    [selectedIds, data, viewMode],
  );

  if (selectedIds.length === 0) {
    return (
      <MacroPlot
        data={[]}
        layout={{}}
        subplotCount={1}
        emptyMessage="请至少选择 1 个指标开始对比"
      />
    );
  }

  if (chart.kind === 'linked') {
    return <LinkedSubplots subplots={chart.subplots} />;
  }

  return (
    <MacroPlot
      data={chart.traces}
      layout={chart.layout}
      subplotCount={chart.subplotCount}
      height={chartHeightForSubplots(chart.subplotCount)}
    />
  );
}

function buildByMode(
  ids: IndicatorId[],
  data: EconomicDataResponse,
  mode: ViewMode,
): BuiltChart {
  if (mode === 'minMax') return buildMinMax(ids, data);
  if (mode === 'normalize') return buildNormalize(ids, data);
  if (mode === 'dualAxisWithCorrelation' && ids.length === 2) {
    return buildDualAxisWithCorrelation(ids, data);
  }
  return buildDualAxis(ids, data);
}

function buildMinMax(ids: IndicatorId[], data: EconomicDataResponse): BuiltChart {
  const dates = data.dates;
  const traces = ids
    .map((id, idx) => {
      const meta = INDICATORS[id];
      const raw = extractSeries(data, id);
      const norm = minMaxNormalize(raw);
      return buildLineTrace(
        {
          label: meta.label,
          color: meta.color,
          unit: '%',
          dash: DASHES[idx % DASHES.length],
          valueFormat: '.1f',
        },
        dates,
        norm,
        {
          customdata: raw as unknown[],
          hovertemplate:
            `<b>${meta.label}</b><br>` +
            `区间百分位: %{y:.1f}%<br>` +
            `原始值: %{customdata}${meta.unit ? ' ' + meta.unit : ''}` +
            `<extra></extra>`,
        },
      );
    })
    .filter(Boolean) as Data[];

  const layout = buildMultiAxisLayout({
    axes: [
      {
        key: 'y',
        title: '区间百分位（0%=最低，100%=最高）',
        axisColor: '#e5e7eb',
        side: 'left',
        range: [-12.5, 112.5],
        zeroline: true,
        zerolinecolor: '#666',
        zerolinewidth: 1,
      },
    ],
  });

  return { kind: 'single', traces, layout: layout as Record<string, unknown>, subplotCount: 1 };
}

function buildNormalize(ids: IndicatorId[], data: EconomicDataResponse): BuiltChart {
  const dates = data.dates;
  const traces = ids
    .map((id, idx) => {
      const meta = INDICATORS[id];
      const raw = extractSeries(data, id);
      const norm = normalize(raw);
      const delta = norm.map((v) => (v == null ? null : v - 100));
      return buildLineTrace(
        {
          label: meta.label,
          color: meta.color,
          dash: DASHES[idx % DASHES.length],
          valueFormat: '.2f',
        },
        dates,
        norm,
        {
          customdata: delta.map((d, i) => [raw[i], d]) as unknown[],
          hovertemplate:
            `<b>${meta.label}</b><br>` +
            `归一化: %{y:.2f}<br>` +
            `涨跌: %{customdata[1]:+.2f}%<br>` +
            `原始值: %{customdata[0]}${meta.unit ? ' ' + meta.unit : ''}` +
            `<extra></extra>`,
        },
      );
    })
    .filter(Boolean) as Data[];

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
  });

  return { kind: 'single', traces, layout: layout as Record<string, unknown>, subplotCount: 1 };
}

function groupByUnit(ids: IndicatorId[]): Array<{ unit: string; ids: IndicatorId[] }> {
  const map = new Map<string, IndicatorId[]>();
  for (const id of ids) {
    const unit = INDICATORS[id].unit || '数值';
    if (!map.has(unit)) map.set(unit, []);
    map.get(unit)!.push(id);
  }
  return [...map.entries()].map(([unit, grouped]) => ({ unit, ids: grouped }));
}

/** 把单位组装进最多 3 个子图，每个子图最多 2 种单位 */
function packUnitGroups(
  groups: Array<{ unit: string; ids: IndicatorId[] }>,
): Array<Array<{ unit: string; ids: IndicatorId[] }>> {
  const slots: Array<Array<{ unit: string; ids: IndicatorId[] }>> = [];
  for (const g of groups) {
    const open = slots.find((s) => s.length < 2);
    if (open) {
      open.push(g);
      continue;
    }
    if (slots.length < 3) {
      slots.push([g]);
      continue;
    }
    slots[slots.length - 1].push(g);
  }
  return slots;
}

function buildDualAxis(ids: IndicatorId[], data: EconomicDataResponse): BuiltChart {
  const unitGroups = groupByUnit(ids);
  if (unitGroups.length <= 2) {
    return buildDualAxisSingle(ids, data);
  }
  return buildDualAxisSubplots(data, packUnitGroups(unitGroups));
}

function buildDualAxisSingle(ids: IndicatorId[], data: EconomicDataResponse): BuiltChart {
  const dates = data.dates;
  const assignment = buildDualAxisAssignment(ids);

  const traces = ids
    .map((id, idx) => {
      const meta = INDICATORS[id];
      const raw = extractSeries(data, id);
      const axisKey = assignment.axisByUnit.get(meta.unit || '数值') || 'y';
      return buildLineTrace(
        {
          label: meta.label,
          color: meta.color,
          unit: meta.unit,
          yaxis: axisKey,
          dash: DASHES[idx % DASHES.length],
          valueFormat: '.2f',
        },
        dates,
        raw,
      );
    })
    .filter(Boolean) as Data[];

  const layout = buildMultiAxisLayout({
    axes: assignment.axes,
  });

  return { kind: 'single', traces, layout: layout as Record<string, unknown>, subplotCount: 1 };
}

function buildDualAxisSubplots(
  data: EconomicDataResponse,
  slots: Array<Array<{ unit: string; ids: IndicatorId[] }>>,
): BuiltChart {
  const dates = data.dates;
  const xKeys: XAxisKey[] = ['x', 'x2', 'x3'];
  const yPairs: Array<[AxisKey, AxisKey]> = [
    ['y', 'y2'],
    ['y3', 'y4'],
    ['y5', 'y6'],
  ];

  const panels: SubplotPanelSpec[] = slots.map((slot, slotIdx) => {
    const [leftKey, rightKey] = yPairs[slotIdx];
    const xAxisKey = xKeys[slotIdx];
    const yAxes = slot.map((group, axisIdx) => {
      const first = INDICATORS[group.ids[0]];
      const isMain = axisIdx === 0;
      return {
        key: isMain ? leftKey : rightKey,
        title: group.unit ? `单位：${group.unit}` : '数值',
        titleColor: first.color,
        axisColor: first.color,
        side: (isMain ? 'left' : 'right') as 'left' | 'right',
        overlaying: isMain ? undefined : leftKey,
      };
    });

    const traces: Data[] = [];
    slot.forEach((group, axisIdx) => {
      const yaxis = axisIdx === 0 ? leftKey : rightKey;
      group.ids.forEach((id, idx) => {
        const meta = INDICATORS[id];
        const t = buildLineTrace(
          {
            label: meta.label,
            color: meta.color,
            unit: meta.unit,
            yaxis,
            xaxis: xAxisKey,
            dash: DASHES[idx % DASHES.length],
            valueFormat: '.2f',
          },
          dates,
          extractSeries(data, id),
        );
        if (t) traces.push(t);
      });
    });

    return { traces, spec: { xAxisKey, yAxes } };
  });

  return { kind: 'linked', subplots: panels };
}

function buildDualAxisWithCorrelation(ids: IndicatorId[], data: EconomicDataResponse): BuiltChart {
  const dates = data.dates;
  const assignment = buildDualAxisAssignment(ids);
  const [a, b] = ids;

  const upperTraces = ids
    .map((id, idx) => {
      const meta = INDICATORS[id];
      const raw = extractSeries(data, id);
      const axisKey = assignment.axisByUnit.get(meta.unit || '数值') || 'y';
      return buildLineTrace(
        {
          label: meta.label,
          color: meta.color,
          unit: meta.unit,
          yaxis: axisKey,
          xaxis: 'x',
          dash: DASHES[idx % DASHES.length],
          valueFormat: '.2f',
        },
        dates,
        raw,
      );
    })
    .filter(Boolean) as Data[];

  const xs = extractSeries(data, a);
  const ys = extractSeries(data, b);
  const corr = rollingCorrelation(xs, ys, CORR_WINDOW, CORR_MIN_SAMPLES);
  const corrTrace = buildLineTrace(
    {
      label: '滚动相关性',
      color: '#fbbf24',
      yaxis: 'y3',
      xaxis: 'x2',
      valueFormat: '.3f',
    },
    dates,
    corr,
  );

  return {
    kind: 'linked',
    subplots: [
      {
        traces: upperTraces,
        spec: {
          xAxisKey: 'x',
          yAxes: assignment.axes.map((axis, idx) => ({
            key: axis.key,
            title: axis.title,
            titleColor: axis.titleColor,
            axisColor: axis.axisColor,
            side: axis.side,
            overlaying: idx === 0 ? undefined : 'y',
          })),
        },
        emptyMessage: '暂无对比数据',
      },
      {
        traces: corrTrace ? [corrTrace] : [],
        spec: {
          xAxisKey: 'x2',
          yAxes: [
            {
              key: 'y3',
              title: `30 日滚动相关性 · ${INDICATORS[a].label} × ${INDICATORS[b].label}`,
              axisColor: '#e5e7eb',
              side: 'left',
              range: [-1.05, 1.05],
              zeroline: true,
              zerolinecolor: '#666',
              zerolinewidth: 1,
            },
          ],
        },
        emptyMessage: '样本不足，无法计算滚动相关性',
      },
    ],
  };
}
