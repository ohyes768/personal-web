/**
 * Modal 组件
 * 复制自 packages/shared-ui/src/Modal.tsx
 * 试点：apps/dividend 拆离 monorepo
 *
 * 无障碍：role=dialog + aria-modal + aria-labelledby（标题 h2 即 accessible name）；
 * 打开时焦点迁入弹框（首个可聚焦元素），Tab/Shift+Tab 在弹框内循环（焦点圈，useFocusTrap），
 * 关闭（Esc / 遮罩 / 按钮）后焦点归还给触发元素。
 * 叠层：Esc 只关最顶层（modal-stack），避免抽屉+弹框叠加时一次 Esc 两层全关。
 */
'use client';

import { useEffect, useRef, useId } from 'react';
import { createPortal } from 'react-dom';
import { useFocusTrap } from './useFocusTrap';
import { pushLayer, popLayer, hasLayerOnTop } from '@/lib/modal-stack';

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
  const titleId = useId(); // 多弹框同开时 aria-labelledby 不冲突
  const rootRef = useRef<HTMLDivElement>(null);
  // 弹层层级 id（pushLayer 的结果存 ref，供 Esc/焦点圈判断谁在最顶层）
  const layerIdRef = useRef<symbol | null>(null);
  // 焦点圈范围 = dialog 内容本体（遮罩不进 Tab 序列）
  const dialogRef = useRef<HTMLDivElement>(null);
  useFocusTrap(isOpen, dialogRef, layerIdRef);

  // 入栈 + Esc（仅最顶层响应）+ body 锁滚
  useEffect(() => {
    if (!isOpen) return;
    const layerId = pushLayer();
    layerIdRef.current = layerId;

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (hasLayerOnTop(layerId)) return; // 有更晚打开的弹层，Esc 先退它
      onClose();
    };
    document.addEventListener('keydown', handleEsc);
    document.body.style.overflow = 'hidden';
    return () => {
      popLayer(layerId);
      layerIdRef.current = null;
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div ref={rootRef} className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 遮罩层：点击关闭（视觉装饰，不进读屏/Tab 序列——aria-modal 已把上下文圈在 dialog 内，
          关闭另有 dialog 内「关闭」按钮与 Esc） */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 弹框内容：dialog 语义，标题 h2 提供 accessible name */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative z-10 w-full ${sizeClasses[size]} ${className} bg-gray-900 border border-gray-700 rounded-xl shadow-2xl max-h-[85vh] overflow-hidden flex flex-col`}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 id={titleId} className="text-lg font-semibold text-gray-100">{title}</h2>
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
