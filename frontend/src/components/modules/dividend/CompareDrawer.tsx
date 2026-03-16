/**
 * 股票对比侧边抽屉组件
 */
'use client';

import { useEffect, useRef } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { CompareDrawerProps } from '@/lib/modules/dividend/types';
import { CompareTable } from './CompareTable';

export function CompareDrawer({
  isOpen,
  onClose,
  stocks,
  onRemove,
  drawerRef,
}: CompareDrawerProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  // 键盘导航：ESC 关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      // 禁用背景滚动
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // 响应式宽度
  const getDrawerWidth = () => {
    if (typeof window === 'undefined') return 'w-[60vw]';

    const width = window.innerWidth;
    if (width >= 1280) return 'w-[900px]';      // xl: 固定 900px
    if (width >= 1024) return 'w-[60vw]';      // lg: 60vw
    if (width >= 768) return 'w-[70vw]';       // md: 70vw
    if (width >= 640) return 'w-[90vw]';       // sm: 90vw
    return 'w-[95vw]';                          // xs: 95vw（接近全屏）
  };

  if (!isOpen) {
    return null;
  }

  return (
    <>
      {/* 背景遮罩 */}
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity duration-300"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 抽屉 */}
      <div
        ref={drawerRef}
        className={`fixed top-0 right-0 bottom-0 z-50 bg-gray-900 shadow-xl transform transition-transform duration-300 flex flex-col ${getDrawerWidth()}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-drawer-title"
        aria-describedby="compare-drawer-description"
        tabIndex={-1}
      >
        {/* 固定头部 */}
        <div className="sticky top-0 z-10 bg-gray-900 border-b border-gray-700">
          <div className="flex items-center justify-between px-6 py-4">
            <h2
              id="compare-drawer-title"
              className="text-lg font-semibold text-white"
            >
              股票对比
            </h2>
            <button
              onClick={onClose}
              className="min-h-10 min-w-10 flex items-center justify-center text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
              aria-label="关闭对比窗口"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
          <p id="compare-drawer-description" className="sr-only">
            对比所选股票的股息率、PE、PB、价格等关键指标
          </p>
        </div>

        {/* 可滚动内容区 */}
        <div ref={contentRef} className="overflow-y-auto flex-1 p-6">
          <CompareTable stocks={stocks} onRemove={onRemove} />
        </div>
      </div>
    </>
  );
}