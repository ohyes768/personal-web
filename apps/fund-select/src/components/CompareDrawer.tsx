/**
 * 对比侧边抽屉（从 dividend 移植，股票→基金文案）
 */
'use client';

import { useEffect, useRef } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

import { CompareTable, type CompareDimension } from './CompareTable';

interface CompareDrawerProps<T> {
  isOpen: boolean;
  onClose: () => void;
  items: T[];
  dimensions: Array<CompareDimension<T>>;
  onRemove: (code: string) => void;
}

export function CompareDrawer<T extends { code: string; name: string }>({
  isOpen, onClose, items, dimensions, onRemove,
}: CompareDrawerProps<T>) {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const width = typeof window === 'undefined'
    ? 'w-[60vw]'
    : window.innerWidth >= 1280 ? 'w-[900px]'
      : window.innerWidth >= 1024 ? 'w-[60vw]'
        : window.innerWidth >= 768 ? 'w-[70vw]'
          : window.innerWidth >= 640 ? 'w-[90vw]'
            : 'w-[95vw]';   // xs 接近全屏

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity duration-300"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={drawerRef}
        className={`fixed top-0 right-0 bottom-0 z-50 bg-gray-900 shadow-xl transform transition-transform duration-300 flex flex-col ${width}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-drawer-title"
        tabIndex={-1}
      >
        <div className="sticky top-0 z-10 bg-gray-900 border-b border-gray-700">
          <div className="flex items-center justify-between px-6 py-4">
            <h2 id="compare-drawer-title" className="text-lg font-semibold text-ink-strong">
              基金对比
            </h2>
            <button
              onClick={onClose}
              className="min-h-10 min-w-10 flex items-center justify-center text-gray-400 hover:text-ink-strong hover:bg-gray-700 rounded transition-colors"
              aria-label="关闭对比窗口"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
        </div>
        <div className="overflow-y-auto flex-1 p-6">
          <CompareTable items={items} dimensions={dimensions} onRemove={onRemove} />
        </div>
      </div>
    </>
  );
}
