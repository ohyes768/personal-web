/**
 * 来源分段控件（11-15-source-segmented）
 *
 * 默认三态「全部 | 三分法 | 市场」，值写入 URL（?source=...）：
 * - all：三分法名单 ∪ 市场子类（债基默认浏览态）
 * - curated：雪球三分法 yaml 名单
 * - market：akshare 市场子类圈定（此时展示市场专属筛选条件）
 *
 * `segments` 可覆盖成两态（股基用）：股基三分法 142 只**全部**含在市场 universe 内，
 * 「全部」与「市场」逐只同集 —— 多一个分段只是噪音，砍掉。三分法成员在「市场」态
 * 用行内徽章标出（见 FundTable 的 showCuratedBadge）。
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
  { key: 'all', label: '全部', title: '三分法名单 ∪ 市场子类' },
  { key: 'curated', label: '三分法', title: '仅雪球三分法名单' },
  { key: 'market', label: '市场', title: '仅市场子类圈定（akshare 全量）' },
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
