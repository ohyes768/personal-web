'use client';

/**
 * 联动子图容器 — 拆分方案核心：
 * - 每个子图独立 MacroPlot，legend 自动落在本子图上方（buildBaseLayout 顶部横排）
 * - x 轴联动：onRelayout 同步 range / autorange 到所有子图
 * - 防循环：Plotly 程序性 relayout 同样触发事件，靠值比较跳过相同 range；
 *   xRange 用 ref 读取，保证 onRelayout 闭包不因 state 更新而过期
 *   （react-plotly.js 只在 updatePlotly 后重绑事件，闭包可能滞后）
 */
import { useCallback, useRef, useState } from 'react';
import {
  buildSubplotLayout,
  chartHeightForSubplots,
  layoutAxisKey,
  type SubplotPanelSpec,
} from '@/lib/utils/plotlyTheme';
import { MacroPlot } from './MacroPlot';

/** 共享 x 轴范围；null = autorange（初始态 / 双击复位态） */
type XRange = [number, number] | [string, string] | null;

const RANGE_EPS = 1e-9;

function rangeEquals(a: XRange, b: XRange): boolean {
  if (a == null || b == null) return a === b;
  if (a.length !== b.length) return false;
  return a.every((v, i) => {
    const o = b[i];
    if (typeof v === 'number' && typeof o === 'number') {
      return Math.abs(v - o) < RANGE_EPS;
    }
    return v === o;
  });
}

export function LinkedSubplots({
  subplots,
  compact = false,
  gapClassName = 'space-y-4',
}: {
  subplots: SubplotPanelSpec[];
  compact?: boolean;
  gapClassName?: string;
}) {
  const [xRange, setXRange] = useState<XRange>(null);
  const xRangeRef = useRef<XRange>(null);

  const handleRelayout = useCallback(
    (panel: SubplotPanelSpec, e: Record<string, unknown>) => {
      const xKey = layoutAxisKey(panel.spec.xAxisKey);

      if (e[`${xKey}.autorange`] === true) {
        if (xRangeRef.current !== null) {
          xRangeRef.current = null;
          setXRange(null);
        }
        return;
      }

      // 用户交互（拖拽/框选缩放）的事件是 range[0] 与 range[1] 两个分开的
      // key；完整数组 xaxis.range 只在程序性 relayout 时出现，两者都要接
      let next: XRange = e[`${xKey}.range`] as XRange;
      const r0 = e[`${xKey}.range[0]`];
      const r1 = e[`${xKey}.range[1]`];
      if (r0 !== undefined && r1 !== undefined) {
        next =
          typeof r0 === 'number' && typeof r1 === 'number'
            ? [r0, r1]
            : [String(r0), String(r1)];
      }

      if (Array.isArray(next) && next.length === 2) {
        if (!rangeEquals(next, xRangeRef.current)) {
          xRangeRef.current = next;
          setXRange(next);
        }
      }
    },
    [],
  );

  return (
    <div className={gapClassName}>
      {subplots.map((panel, idx) => (
        <MacroPlot
          key={idx}
          data={panel.traces}
          layout={buildSubplotLayout({ spec: panel.spec, compact, xRange })}
          height={panel.height ?? chartHeightForSubplots(1, compact)}
          emptyMessage={panel.emptyMessage}
          onRelayout={(e) => handleRelayout(panel, e)}
        />
      ))}
    </div>
  );
}
