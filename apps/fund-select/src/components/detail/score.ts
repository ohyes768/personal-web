/**
 * 评分工具：把每个指标映射成 0-4 段（灯）+ 综合分 0-100
 *
 * 阈值参考：
 *   - 夏普 <0 / 0-0.5 / 0.5-1 / 1-1.5 / ≥1.5
 *   - IR <0 / 0-0.3 / 0.3-0.6 / 0.6-1 / ≥1
 *   - 选股α (年化) <-5% / -5~0% / 0~5% / 5~10% / ≥10%
 *   - 择时γ (年化) <-0.05 / -0.05~0 / 0~0.05 / 0.05~0.1 / ≥0.1
 *   - α-IR <0 / 0-0.3 / 0.3-0.6 / 0.6-1 / ≥1
 *   - 超额 3y <-10% / -10~0% / 0~20% / 20~40% / ≥40%
 */
import type { FundDetail } from '@/lib/types';

/** 0-4 段（5 段灯），null 表示无数据 → 灯全暗 */
export type Segment = 0 | 1 | 2 | 3 | 4;

/** 5 段灯颜色（暖白主题，深绿→中性米→警示红） */
export const SIGNAL_PALETTE = [
  'var(--color-rank-bottom)',    // 段 0：警示（红）
  'var(--color-rank-bottom-soft)', // 段 1：偏弱（浅红）
  'var(--color-rank-mid)',       // 段 2：中性（米）
  'var(--color-rank-top-soft)',  // 段 3：良好（浅绿）
  'var(--color-rank-top)',       // 段 4：优秀（深绿）
] as const;

const NONE: Segment = 0;

function band<T>(v: number, thresholds: [number, Segment][]): Segment {
  for (const [t, seg] of thresholds) if (v >= t) return seg;
  return 0;
}

export function scoreSharpe(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  return band(v, [[1.5, 4], [1.0, 3], [0.5, 2], [0, 1]]);
}

export function scoreIR(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  return band(v, [[1.0, 4], [0.6, 3], [0.3, 2], [0, 1]]);
}

/** α / 超额字段存的是年化小数（0.05 = 5%），按百分位比较 */
export function scoreAlpha(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  const pct = v * 100;
  return band(pct, [[10, 4], [5, 3], [0, 2], [-5, 1]]);
}

export function scoreGamma(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  return band(v, [[0.1, 4], [0.05, 3], [0, 2], [-0.05, 1]]);
}

export function scoreAlphaIR(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  return band(v, [[1, 4], [0.6, 3], [0.3, 2], [0, 1]]);
}

export function scoreExcess3y(v: number | null | undefined): Segment {
  if (v == null) return NONE;
  const pct = v * 100;
  return band(pct, [[40, 4], [20, 3], [0, 2], [-10, 1]]);
}

/** 综合分 0-100：把 6 个段（0-4）相加 ÷ 24 × 100，缺失按 0 算 */
export function compositeScore(detail: FundDetail): {
  score: number;
  segment: Segment;
  parts: Record<string, Segment>;
} {
  const parts: Record<string, Segment> = {
    sharpe: scoreSharpe(detail.sharpe),
    ir: scoreIR(detail.ir),
    alpha: scoreAlpha(detail.alpha),
    gamma: scoreGamma(detail.gamma),
    alpha_ir: scoreAlphaIR(detail.alpha_ir),
    excess_3y: scoreExcess3y(detail.excess_3y),
  };
  const sum = Object.values(parts).reduce<number>((s, v) => s + v, 0);
  const score = Math.round((sum / 24) * 100);
  const segment = band(score, [[90, 4], [75, 3], [60, 2], [40, 1]]);
  return { score, segment, parts };
}

/** 综合评级中文标签 */
export function gradeLabel(seg: Segment): string {
  switch (seg) {
    case 4: return '卓越';
    case 3: return '优秀';
    case 2: return '良好';
    case 1: return '偏弱';
    default: return '警示';
  }
}

/** 综合评级的英文标签（小写衬线、用于徽章副标题） */
export function gradeLabelEn(seg: Segment): string {
  switch (seg) {
    case 4: return 'elite';
    case 3: return 'excellent';
    case 2: return 'solid';
    case 1: return 'weak';
    default: return 'risk';
  }
}
