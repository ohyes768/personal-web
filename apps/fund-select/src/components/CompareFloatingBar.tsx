/**
 * 对比底部浮动栏（从 dividend 移植，股票→基金文案）
 */
'use client';

interface CompareFloatingBarProps {
  selectedCount: number;
  selectedNames: string[];
  maxSelect: number;
  onOpenCompare: () => void;
  onClear: () => void;
  isVisible: boolean;
}

export function CompareFloatingBar({
  selectedCount, selectedNames, maxSelect, onOpenCompare, onClear, isVisible,
}: CompareFloatingBarProps) {
  if (!isVisible || selectedCount === 0) {
    return null;
  }

  const progressDots = Array.from({ length: maxSelect }).map((_, i) => (
    <span
      key={i}
      className={`w-2 h-2 rounded-full transition-colors ${
        i < selectedCount ? 'bg-blue-500' : 'bg-gray-600'
      }`}
    />
  ));

  const display = selectedNames.slice(0, 3);
  const remaining = selectedCount - 3;
  const namesDisplay = remaining > 0
    ? `${display.join('·')} 等${selectedCount}只`
    : display.join('·');

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-gray-800 border-t border-gray-700 shadow-lg">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-8">
        <div className="flex items-center justify-between h-14 gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <button
              onClick={onClear}
              className="px-3 py-1.5 text-sm text-gray-300 hover:text-ink-strong hover:bg-gray-700 rounded transition-colors"
              aria-label="清空已选基金"
            >
              清空
            </button>
            <div className="flex items-center gap-2 text-sm text-gray-300 whitespace-nowrap">
              <span>已选 {selectedCount}/{maxSelect}</span>
              <div className="flex items-center gap-1 ml-1">{progressDots}</div>
            </div>
          </div>

          <div className="flex items-center justify-center flex-1 min-w-0">
            <span className="text-sm text-gray-200 truncate" title={namesDisplay}>
              {namesDisplay}
            </span>
          </div>

          <button
            onClick={onOpenCompare}
            disabled={selectedCount < 2}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded transition-colors whitespace-nowrap"
            aria-label={`开始对比${selectedCount}只基金`}
          >
            开始对比
          </button>
        </div>
      </div>
    </div>
  );
}
