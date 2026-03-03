/**
 * 时间范围选择器组件
 */
import type { TimeRange } from '@/lib/types/economic';

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
}

const TIME_RANGES: Array<{ label: string; value: TimeRange }> = [
  { label: '1个月', value: '1M' },
  { label: '3个月', value: '3M' },
  { label: '6个月', value: '6M' },
  { label: '1年', value: '1Y' },
  { label: '3年', value: '3Y' },
  { label: '全部', value: 'ALL' },
];

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {TIME_RANGES.map((range) => (
        <button
          key={range.value}
          onClick={() => onChange(range.value)}
          className={`rounded-lg px-4 py-2 transition-colors ${
            value === range.value
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
          }`}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}
