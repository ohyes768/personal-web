'use client';

/**
 * 月度分组卡片网格（4 张：货币政策 / 信用扩张 / 经济运行 / 通胀）
 */
import type { MacroSignalSnapshot } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';
import { MONTHLY_GROUPS } from './constants';
import { GroupCard } from './GroupCard';

interface GroupCardGridProps {
  snapshot: MacroSignalSnapshot;
  selectedMonth: string;
  onJumpToTab?: (tab: TabType) => void;
}

export function GroupCardGrid({ snapshot, selectedMonth, onJumpToTab }: GroupCardGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {MONTHLY_GROUPS.map(key => (
        <GroupCard
          key={key}
          groupKey={key}
          group={snapshot.groups[key]}
          selectedMonth={selectedMonth}
          onJumpToTab={onJumpToTab}
        />
      ))}
    </div>
  );
}
