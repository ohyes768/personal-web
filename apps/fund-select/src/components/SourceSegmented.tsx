/**
 * 来源分段控件（11-15-source-segmented）
 *
 * 两态「市场 | 三分法」，值写入 URL（?source=...）：
 * - market：akshare 市场子类圈定（该 tab 的全集；此时展示市场专属筛选条件）
 * - curated：雪球三分法 yaml 名单
 *
 * 「全部」（三分法 ∪ 市场）已从 UI 下线：两个 tab 下它与某一态**逐行同集**
 * （股基 all ≡ market、债基 all ≡ curated）→ 只是噪音。后端仍支持 source=all
 * （API 兼容），老链接 ?source=all 会被 parseSource 归一到该 tab 的默认分段。
 *
 * 样式对齐 FundsNavigation 的选中态（bg-accent / text-ink-muted）。
 */
'use client';

import type { SourceSegment } from '@/lib/types';

export interface SourceSegmentOption {
  key: SourceSegment;
  label: string;
  title: string;
}

const SEGMENTS: SourceSegmentOption[] = [
  { key: 'market', label: '市场', title: 'akshare 市场子类圈定（全量）' },
  { key: 'curated', label: '三分法', title: '仅雪球三分法名单' },
];

export function SourceSegmented({
  value,
  onChange,
  segments = SEGMENTS,
}: {
  value: SourceSegment;
  onChange: (next: SourceSegment) => void;
  /** 覆盖可选分段（两态用法） */
  segments?: SourceSegmentOption[];
}) {
  return (
    <div
      className="flex items-center gap-1 text-sm"
      role="radiogroup"
      aria-label="基金来源"
    >
      <span className="text-ink-muted mr-0.5">来源</span>
      {segments.map(seg => (
        <button
          key={seg.key}
          type="button"
          role="radio"
          aria-checked={value === seg.key}
          title={seg.title}
          onClick={() => onChange(seg.key)}
          className={`px-2 py-0.5 rounded transition-colors ${
            value === seg.key
              ? 'bg-accent text-white'
              : 'text-ink-muted hover:text-ink-strong border border-rule'
          }`}
        >
          {seg.label}
        </button>
      ))}
    </div>
  );
}
