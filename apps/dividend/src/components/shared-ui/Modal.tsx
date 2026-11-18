/**
 * Modal 组件
 * 复制自 packages/shared-ui/src/Modal.tsx
 * 试点：apps/dividend 拆离 monorepo
 */
'use client';

import { useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  /**
   * 底部固定操作区：渲染在正文滚动区之外。
   * 长报告（正文自身可滚动）用它把操作按钮钉在弹框底部——
   * 正文不要再套一层 overflow 容器，否则会出现两条竖向滚动条。
   */
  footer?: React.ReactNode;
}

const sizeClasses = {
  xs: 'max-w-xs',   // 320px - 超小
  sm: 'max-w-sm',   // 384px - 小
  md: 'max-w-2xl',  // 672px - 中
  lg: 'max-w-4xl',  // 896px - 大
  xl: 'max-w-6xl',  // 1152px - 特大
};

export function Modal({ isOpen, onClose, title, children, size = 'md', className = '', footer }: ModalProps) {
  const handleEsc = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleEsc);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleEsc]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 遮罩层 - 渐变暗色背景 */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        role="button"
        tabIndex={0}
        aria-label="关闭"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClose();
          }
        }}
      />

      {/* 弹框内容 */}
      <div className={`relative z-10 w-full ${sizeClasses[size]} ${className} bg-gray-900 border border-gray-700 rounded-xl shadow-2xl max-h-[85vh] overflow-hidden flex flex-col`}>
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
          <button
            onClick={onClose}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center text-gray-400 hover:text-ink-strong hover:bg-paper-tint focus:outline-none focus:ring-2 focus:ring-info rounded-md transition-colors cursor-pointer"
            aria-label="关闭"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容区：唯一竖向滚动区 */}
        <div className="flex-1 overflow-y-auto p-6">
          {children}
        </div>

        {/* 底部固定操作区：不随正文滚动 */}
        {footer && (
          <div className="flex-none border-t border-gray-700 px-6 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
