/**
 * 股票对比底部浮动栏组件
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';
import { CompareFloatingBarProps } from '@/lib/modules/dividend/types';

export function CompareFloatingBar({
  selectedCount,
  selectedStocks,
  maxSelect,
  onOpenCompare,
  onClear,
  isVisible,
}: CompareFloatingBarProps) {
  if (!isVisible || selectedCount === 0) {
    return null;
  }

  // 进度指示器
  const progressDots = Array.from({ length: maxSelect }).map((_, i) => (
    <span
      key={i}
      className={`w-2 h-2 rounded-full transition-colors ${
        i < selectedCount ? 'bg-blue-500' : 'bg-gray-600'
      }`}
    />
  ));

  // 显示股票名称（最多3个）
  const displayStocks = selectedStocks.slice(0, 3);
  const remainingCount = selectedCount - 3;
  const stockNames = displayStocks.map(s => s.name).join('·');
  const stockDisplay = remainingCount > 0
    ? `${stockNames} 等${selectedCount}只`
    : stockNames;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-gray-800 border-t border-gray-700 shadow-lg transform transition-transform duration-300">
      <div className="container mx-auto px-8 lg:px-16">
        <div className="flex items-center justify-between h-14 gap-4">
          {/* 左侧：清空按钮 + 进度 */}
          <div className="flex items-center gap-4 min-w-0">
            <button
              onClick={onClear}
              className="px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded transition-colors"
              aria-label="清空已选股票"
            >
              清空
            </button>
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <span>已选 {selectedCount}/{maxSelect}</span>
              <div className="flex items-center gap-1 ml-2">
                {progressDots}
              </div>
            </div>
          </div>

          {/* 中间：股票名称 */}
          <div className="flex items-center justify-center flex-1 min-w-0">
            <span className="text-sm text-gray-200 truncate" title={stockDisplay}>
              {stockDisplay}
            </span>
          </div>

          {/* 右侧：开始对比按钮 */}
          <button
            onClick={onOpenCompare}
            disabled={selectedCount < 2}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded transition-colors"
            aria-label={`开始对比${selectedCount}只股票`}
          >
            开始对比
          </button>
        </div>
      </div>
    </div>
  );
}