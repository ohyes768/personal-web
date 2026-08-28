'use client';

/**
 * 日频日期切换器:前一交易日 / 日期下拉 / 后一交易日
 * - dates 由 daily-snapshot 接口返回(降序,近 60 个交易日 ∪ 今日)
 * - ◀▶ 在 dates 数组内步进,天然跳过非交易日
 * - 切到最新( dates[0] )时 ▶ 禁用,切到最旧时 ◀ 禁用
 */
interface DailySwitcherProps {
  currentDate: string;      // 'YYYY-MM-DD'
  availableDates: string[]; // 降序
  onChange: (date: string) => void;
}

function formatDateLabel(date: string, isToday: boolean): string {
  const [, m, d] = date.split('-');
  return `${parseInt(m, 10)} 月 ${parseInt(d, 10)} 日${isToday ? '(今日)' : ''}`;
}

export function DailySwitcher({ currentDate, availableDates, onChange }: DailySwitcherProps) {
  // dates 降序 → ascending = 升序,便于前后步进
  const ascending = [...availableDates].sort();
  const minDate = ascending[0];
  const maxDate = ascending[ascending.length - 1];
  /** dates 未就绪 或 当前日期不在列表里 → 切换按钮全部禁用 */
  const canSwitch = ascending.length > 0 && ascending.includes(currentDate);
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  const handlePrev = () => {
    const idx = ascending.indexOf(currentDate);
    if (idx > 0) onChange(ascending[idx - 1]);
  };
  const handleNext = () => {
    const idx = ascending.indexOf(currentDate);
    if (idx >= 0 && idx < ascending.length - 1) onChange(ascending[idx + 1]);
  };

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <button
        type="button"
        onClick={handlePrev}
        disabled={!canSwitch || currentDate <= minDate}
        className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ← 前一日
      </button>
      <div className="relative">
        <select
          value={currentDate}
          onChange={e => onChange(e.target.value)}
          disabled={!canSwitch}
          className="appearance-none bg-gray-800 text-white px-6 py-2 pr-10 rounded-lg border border-gray-700 hover:bg-gray-700 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {availableDates.length === 0 ? (
            <option value="" disabled>加载中…</option>
          ) : (
            // 下拉按新→旧排列(与 dates 一致),最近的日期一眼可见
            availableDates.map(d => (
              <option key={d} value={d}>{formatDateLabel(d, d === todayStr)}</option>
            ))
          )}
        </select>
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">▼</span>
      </div>
      <button
        type="button"
        onClick={handleNext}
        disabled={!canSwitch || currentDate >= maxDate}
        className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        后一日 →
      </button>
    </div>
  );
}
