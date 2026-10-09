'use client';

import { useEffect, useState } from 'react';
import { buildSubplotLayout, chartHeightForSubplots, type ChartContext, type DateRange, type SubplotPanelSpec } from '@/lib/utils/chartTheme';
import { MacroEChart } from './MacroEChart';

/** Independent charts share dates, never ECharts instances or mutable option objects. */
export function LinkedSubplots({ subplots, chartId, compact = false, gapClassName = 'space-y-4', onContextChange }: {
  subplots: SubplotPanelSpec[]; chartId: string; compact?: boolean; gapClassName?: string;
  onContextChange?: (context: ChartContext) => void;
}) {
  const [range, setRange] = useState<DateRange>(null);
  useEffect(() => { setRange(null); }, [subplots]);
  return <div className={gapClassName}>
    {subplots.map((panel) => <MacroEChart key={panel.id ?? panel.spec.xAxisKey}
      chartId={panel.id ?? `${chartId}.${panel.spec.xAxisKey}`} data={panel.traces}
      layout={buildSubplotLayout({ spec: panel.spec, compact })}
      height={panel.height ?? chartHeightForSubplots(1, compact)} emptyMessage={panel.emptyMessage}
      range={range} onRangeChange={setRange} onContextChange={onContextChange} />)}
  </div>;
}
