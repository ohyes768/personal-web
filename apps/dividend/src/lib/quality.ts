/**
 * 基本面评级（Hermes 五维评分）类型与工具
 * 评分契约见 backend/dividend-select/skills/basic-quality-rating/SKILL.md（自动化 JSON 输出模式）
 */
import type { RefreshJob } from './types';

export const QUALITY_DIMENSION_ORDER = ['business', 'moat', 'industry', 'management', 'financial'] as const;
export type QualityDimensionKey = (typeof QUALITY_DIMENSION_ORDER)[number];

export const QUALITY_DIMENSION_LABELS: Record<QualityDimensionKey, string> = {
  business: '业务模式',
  moat: '护城河',
  industry: '行业前景',
  management: '管理层',
  financial: '财务质量',
};

export interface QualityScore {
  code: string;
  name: string;
  dimensions: Record<QualityDimensionKey, number>;
  weighted_score: number;
  stars: number;
  boundary: string | null;
  summary: string;
  risks: string[];
  watch_points: string[];
  report_md: string;
  scored_at: string;
  data_date: string;
}

export type QualityJob = RefreshJob & { kind: 'quality' };
export interface QualityScoresResponse {
  total: number;
  scores: Record<string, QualityScore>;
  hermes_configured: boolean;
}

/** 加权总分 → 星级（与 SKILL.md / 后端 _stars_for 逐字一致） */
export function starsFor(score: number): number {
  if (score >= 4.5) return 5;
  if (score >= 4.0) return 4;
  if (score >= 3.0) return 3;
  if (score >= 2.0) return 2;
  return 1;
}

/** 五维分简写（固定顺序），如 4/5/3/3/5；缺评分返回 null */
export function dimensionShorthand(dimensions: QualityScore['dimensions'] | undefined): string | null {
  if (!dimensions) return null;
  if (!QUALITY_DIMENSION_ORDER.every(key => Number.isFinite(dimensions[key]))) return null;
  return QUALITY_DIMENSION_ORDER.map(key => dimensions[key]).join('/');
}

/** 星级徽章样式：5-4 星绿、3 星琥珀、2-1 星红（纸感 UI 用文字色而非底色） */
export function starBadgeClass(stars: number): string {
  if (stars >= 4) return 'text-emerald-700';
  if (stars === 3) return 'text-amber-700';
  return 'text-red-700';
}

/** job 是否仍在进行中（需继续轮询） */
export function qualityJobActive(job: Pick<QualityJob, 'status'>): boolean {
  return job.status === 'queued' || job.status === 'running';
}

/** job 终态的用户提示文案 */
export function qualityFinishMessage(job: QualityJob): string {
  if (job.status === 'succeeded') return `评级完成：成功 ${job.succeeded} 只`;
  if (job.status === 'partial_failed') {
    return `评级完成：成功 ${job.succeeded} 只，失败 ${job.failed} 只（${job.failed_codes.join('、')}），可重试失败项`;
  }
  return `评级失败：${job.error || job.message || '请稍后重试'}`;
}
