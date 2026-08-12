'use client';

/**
 * 月份切换器:上一月 / 月份下拉 / 下一月
 * - 月份下拉基于 availableMonths 排序生成
 * - 切到最小/最大月份时,对应方向的按钮 disabled
 */
interface MonthSwitcherProps {
  currentMonth: string;             // 'YYYY-MM'
  availableMonths: string[];        // 可切换月份列表
  onChange: (month: string) => void;
}

function formatMonthLabel(month: string): string {
  const [y, m] = month.split('-');
  return `${y} 年 ${parseInt(m, 10)} 月`;
}

export function MonthSwitcher({ currentMonth, availableMonths, onChange }: MonthSwitcherProps) {
  const sorted = [...availableMonths].sort();
  const minMonth = sorted[0];
  const maxMonth = sorted[sorted.length - 1];

  const handlePrev = () => {
    const idx = sorted.indexOf(currentMonth);
    if (idx > 0) onChange(sorted[idx - 1]);
  };
  const handleNext = () => {
    const idx = sorted.indexOf(currentMonth);
    if (idx >= 0 && idx < sorted.length - 1) onChange(sorted[idx + 1]);
  };

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <button
        type="button"
        onClick={handlePrev}
        disabled={currentMonth <= minMonth}
        className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ← 上一月
      </button>
      <div className="relative">
        <select
          value={currentMonth}
          onChange={e => onChange(e.target.value)}
          className="appearance-none bg-gray-800 text-white px-6 py-2 pr-10 rounded-lg border border-gray-700 hover:bg-gray-700 cursor-pointer"
        >
          {sorted.map(m => (
            <option key={m} value={m}>{formatMonthLabel(m)}</option>
          ))}
        </select>
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">▼</span>
      </div>
      <button
        type="button"
        onClick={handleNext}
        disabled={currentMonth >= maxMonth}
        className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        下一月 →
      </button>
    </div>
  );
}
