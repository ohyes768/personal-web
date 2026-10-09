import type { EChartsOption, LineSeriesOption } from 'echarts';
import type { ChartLayout, ChartSeries, DateRange } from './chartTheme';

export function chartDates(lines: ChartSeries[]): string[] {
  return [...new Set(lines.flatMap((line) => line.dates))].sort();
}
export function dateRangeFromZoom(dates: string[], start = 0, end = 100): DateRange {
  if (!dates.length || (start <= 0 && end >= 100)) return null;
  const last = dates.length - 1;
  return [dates[Math.round(last * start / 100)], dates[Math.round(last * end / 100)]];
}
export function clampRange(dates: string[], range: DateRange): DateRange {
  if (!dates.length || !range) return null;
  const start = dates.find((d) => d >= range[0]) ?? dates[dates.length - 1];
  const end = [...dates].reverse().find((d) => d <= range[1]) ?? dates[0];
  return start <= end ? [start, end] : [dates[0], dates[dates.length - 1]];
}
export function formatValue(value: number | null | undefined, decimals = 2): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}
export function tooltipLines(line: ChartSeries, date: string): string[] {
  const index = line.dates.indexOf(date);
  const result = [`${line.name}：${formatValue(line.values[index], line.decimals)}${line.unit ? ` ${line.unit}` : ''}`];
  for (const detail of line.details ?? []) {
    result.push(`${detail.label}：${formatValue(detail.values[index], detail.decimals ?? 4)}${detail.unit ? ` ${detail.unit}` : ''}`);
  }
  return result;
}
export function buildEChartsOption(
  lines: ChartSeries[], layout: ChartLayout, range: DateRange, narrow = false,
): EChartsOption {
  if (!lines.length) return { series: [], xAxis: [], yAxis: [], dataZoom: [] };
  const dates = chartDates(lines);
  const selectedRange = clampRange(dates, range);
  const axisIndex = new Map(layout.axes.map((axis, index) => [axis.key, index]));
  const series: LineSeriesOption[] = lines.map((line) => {
    const byDate = new Map(line.dates.map((date, index) => [date, line.values[index]]));
    const style = line.dash === 'dashdot' ? [8, 4, 2, 4] : line.dash === 'dot' ? 'dotted' : line.dash === 'solid' ? 'solid' : 'dashed';
    return {
      id: line.id, name: line.name, type: 'line', yAxisIndex: axisIndex.get(line.axis) ?? 0,
      data: dates.map((date) => byDate.get(date) ?? null), connectNulls: false,
      showSymbol: line.markers, symbolSize: 6, symbol: 'circle',
      lineStyle: { color: line.color, width: line.width, type: style },
      itemStyle: { color: line.color }, emphasis: { focus: 'series' },
      ...(layout.axes[axisIndex.get(line.axis) ?? 0]?.zeroline ? {
        markLine: { silent: true, symbol: 'none', label: { show: false },
          lineStyle: { color: '#666', width: 1 }, data: [{ yAxis: 0 }] },
      } : {}),
    };
  });
  return {
    animation: false, backgroundColor: '#1a1a1a', textStyle: { color: '#e5e7eb', fontSize: 11 },
    grid: { left: narrow ? 8 : 16, right: 32, top: 24, bottom: 62, containLabel: true },
    // React owns the legend, so labels wrap instead of being cut off on phones.
    legend: { show: false },
    tooltip: {
      trigger: 'axis', renderMode: 'richText', confine: true,
      backgroundColor: '#111827', borderColor: '#4b5563', textStyle: { color: '#e5e7eb', fontSize: 11 },
      axisPointer: { type: 'line', lineStyle: { color: '#6b7280' } },
      formatter: (params) => {
        const entries = Array.isArray(params) ? params : [params];
        const date = String(entries[0]?.name ?? '');
        const visibleNames = new Set(entries.map((entry) => entry.seriesName));
        return [date, ...lines.filter((line) => visibleNames.has(line.name)).flatMap((line) => tooltipLines(line, date))].join('\n');
      },
    },
    xAxis: { type: 'category', data: dates, boundaryGap: false,
      axisLine: { lineStyle: { color: '#4b5563' } }, axisTick: { show: false },
      axisLabel: { color: '#9ca3af', hideOverlap: true, showMinLabel: true, showMaxLabel: true, alignMinLabel: 'left', alignMaxLabel: 'right', formatter: (date: string) => date.slice(2) },
      splitLine: { show: false },
    },
    yAxis: layout.axes.map((axis, index) => ({
      type: 'value', name: '', position: axis.side ?? (index === 0 ? 'left' : 'right'),
      scale: true, ...(axis.range ? { min: axis.range[0], max: axis.range[1] } : {}),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: axis.axisColor, hideOverlap: true,
        formatter: (v: number) => Math.abs(v) >= 10000 ? `${+(v / 10000).toFixed(1)}万` : `${+v.toFixed(3)}` },
      splitLine: { show: axis.showgrid ?? index === 0, lineStyle: { color: '#2a2a2a' } },
    })),
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false,
        moveOnMouseMove: true, ...(selectedRange ? { startValue: selectedRange[0], endValue: selectedRange[1] } : { start: 0, end: 100 }) },
      { type: 'slider', xAxisIndex: 0, filterMode: 'none', bottom: 6, height: 20,
        showDetail: false, borderColor: '#374151', textStyle: { color: '#9ca3af' },
        ...(selectedRange ? { startValue: selectedRange[0], endValue: selectedRange[1] } : { start: 0, end: 100 }) },
    ],
    series,
  };
}
