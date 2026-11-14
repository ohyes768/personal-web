/**
 * 来源分段控件（11-15-source-segmented）
 *
 * 「全部 | 三分法 | 市场」三态切换，值写入 URL（?source=...）。
 * - all：三分法名单 ∪ 市场子类（默认浏览态）
 * - curated：雪球三分法 yaml 名单
 * - market：akshare 市场子类圈定（此时展示市场专属筛选条件）
 *
 * 样式对齐 FundsNavigation 的选中态（bg-accent / text-ink-muted）。
 */
'use client';

import type { SourceSegment } from '@/lib/types';

const SEGMENTS: { key: SourceSegment; label: string; title: string }[] = [
  { key: 'all', label: '全部', title: '三分法名单 ∪ 市场子类' },
  { key: 'curated', label: '三分法', title: '仅雪球三分法名单' },
  { key: 'market', label: '市场', title: '仅市场子类圈定（akshare 全量）' },
];

export function SourceSegmented({
  value,
  onChange,
}: {
  value: SourceSegment;
  onChange: (next: SourceSegment) => void;
}) {
  return (
    <div
      className="flex items-center gap-1 text-sm"
      role="radiogroup"
      aria-label="基金来源"
    >
      <span className="text-ink-muted mr-0.5">来源</span>
      {SEGMENTS.map(seg => (
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
