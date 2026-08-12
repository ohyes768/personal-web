/**
 * 对比模块 — 双轴布局工具
 *
 * 按 unit 种类把指标分配到左右两个 Y 轴：
 * - 第 1 种 unit → 左轴 'y'（主轴）
 * - 第 2 种 unit → 右轴 'y2'（overlaying 'y'）
 * - 超过 2 种 unit → 第 3+ 种强并到右轴（调用方可提示「单位过多」）
 *
 * 轴标题颜色 = 该 unit 组下第 1 条曲线的颜色（视觉上把轴和曲线绑定）
 */
import type { AxisSpec, AxisKey } from '@/lib/utils/plotlyTheme';
import type { IndicatorId, IndicatorMeta } from './types';
import { INDICATORS } from './indicators';

export interface DualAxisAssignment {
  /** unit → 轴 key，供 trace.yaxis 使用 */
  axisByUnit: Map<string, AxisKey>;
  /** 轴定义（按出现顺序：[左轴, 右轴?]） */
  axes: AxisSpec[];
  /** 是否有 3+ 种 unit 被强并到右轴 */
  overloaded: boolean;
}

/**
 * 给选中的指标构造双轴分配方案
 */
export function buildDualAxisAssignment(ids: IndicatorId[]): DualAxisAssignment {
  const unitOrder: string[] = [];
  const unitToFirstColor: Record<string, string> = {};
  const unitToFirstLabel: Record<string, string> = {};

  for (const id of ids) {
    const meta: IndicatorMeta = INDICATORS[id];
    const u = meta.unit || '数值';
    if (!(u in unitToFirstColor)) {
      unitOrder.push(u);
      unitToFirstColor[u] = meta.color;
      unitToFirstLabel[u] = meta.label;
    }
  }

  const axisByUnit = new Map<string, AxisKey>();
  const axes: AxisSpec[] = [];
  const overloaded = unitOrder.length > 2;

  unitOrder.forEach((u, idx) => {
    const axisKey: AxisKey = idx === 0 ? 'y' : 'y2';
    axisByUnit.set(u, axisKey);
    // 同一个轴只构造一次（第 3+ 种 unit 复用 y2）
    const existing = axes.find((a) => a.key === axisKey);
    if (!existing) {
      const isMain = axisKey === 'y';
      axes.push({
        key: axisKey,
        title: u ? `单位：${u}` : '数值',
        titleColor: unitToFirstColor[u],
        axisColor: unitToFirstColor[u],
        side: isMain ? 'left' : 'right',
        ...(isMain ? {} : { overlaying: 'y' as const, position: 1 }),
      });
    }
  });

  return { axisByUnit, axes, overloaded };
}
