/**
 * 时间范围选择器组件
 */
import type { TimeRange, TIME_RANGES } from '@/lib/modules/fund-flow/types';

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const ranges: readonly TimeRange[] = ['1M', '3M', '6M', '1Y', 'ALL'] as const;

  return (
    <div className="flex gap-2 mb-4">
      {ranges.map((range) => (
        <button
          key={range}
          onClick={() => onChange(range)}
          className={`
            px-4 py-2 rounded font-medium transition-all
            ${value === range
              ? 'bg-[#2962ff] text-white'
              : 'bg-[#1e222d] text-[#d1d4dc] hover:bg-[#2a2e39]'
            }
          `}
        >
          {range}
        </button>
      ))}
    </div>
  );
}