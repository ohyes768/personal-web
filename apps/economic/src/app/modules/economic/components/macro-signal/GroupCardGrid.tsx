'use client';

/**
 * 6 张分组卡片网格(响应式:mobile 1 列、sm 2 列、lg 3 列)
 */
import type { MacroSignalSnapshot } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';
import { GROUP_ORDER } from './constants';
import { GroupCard } from './GroupCard';

interface GroupCardGridProps {
  snapshot: MacroSignalSnapshot;
  selectedMonth: string;
  onJumpToTab?: (tab: TabType) => void;
}

export function GroupCardGrid({ snapshot, selectedMonth, onJumpToTab }: GroupCardGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {GROUP_ORDER.map(key => (
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
