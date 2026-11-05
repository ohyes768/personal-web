/**
 * 入选规则只读说明卡（R5/R7：展示规则来自后端 profile，前端不做规则编辑器）
 *
 * - 入选条件从 profile.filters 渲染（describeEntryFilters）
 * - 市场来源附加采集预筛约束说明（describePrefilters）
 * - 展示来源/口径/版本：累计周数只按同一来源/版本计算（R8 版本隔离）
 */
'use client';

import {
  describeEntryFilters,
  describePrefilters,
  type SharpeBoardProfile,
} from '@/lib/sharpe-board';

const SOURCE_LABEL: Record<string, string> = {
  'discovery-stock': '股基·市场',
  'stock': '股基·雪球三分法',
};

export function SharpeBoardProfileCard({ profile }: { profile: SharpeBoardProfile }) {
  const entry = describeEntryFilters(profile);
  const pre = describePrefilters(profile);
  return (
    <section
      aria-label="入选规则说明"
      className="px-3 py-2.5 bg-paper-card rounded-lg border border-rule text-xs leading-5 text-ink-muted"
    >
      <p>
        <span className="font-medium text-ink-strong">入选规则（每周六自动采集后发布）：</span>
        {entry.length > 0 ? entry.join(' · ') : '以榜单记录时的固定规则为准'}
        <span className="ml-2">
          （来源 {SOURCE_LABEL[profile.source] ?? profile.source} · 规则版本 {profile.version} · 口径 {profile.algorithm_version}）
        </span>
      </p>
      {pre.length > 0 && (
        <p className="mt-1">
          <span className="font-medium text-ink-strong">采集预筛约束：</span>
          市场来源记录范围受全量刷新预筛限制（{pre.join(' · ')}），预筛外的基金不进入记录。
        </p>
      )}
    </section>
  );
}
