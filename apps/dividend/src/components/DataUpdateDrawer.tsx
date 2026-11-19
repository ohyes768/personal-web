'use client';

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useFocusTrap } from './shared-ui/useFocusTrap';
import { pushLayer, popLayer, hasLayerOnTop } from '@/lib/modal-stack';

interface DataUpdateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenScheduler: () => void;
  children: React.ReactNode;
}

/**
 * 数据更新抽屉。
 * 弹层规范与 Modal 对齐：role=dialog + aria-modal + aria-labelledby（标题 h2 即 accessible name）、
 * 焦点迁入/焦点圈/归还（useFocusTrap）、Esc 只关最顶层（modal-stack，叠开弹框时 Esc 先退弹框）。
 * 遮罩挡住底层交互——副标题如实说「暂停浏览」，不写「不会中断」。
 */
export function DataUpdateDrawer({ isOpen, onClose, onOpenScheduler, children }: DataUpdateDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const layerIdRef = useRef<symbol | null>(null);
  useFocusTrap(isOpen, drawerRef, layerIdRef);

  // 入栈 + Esc（仅最顶层响应）
  useEffect(() => {
    if (!isOpen) return;
    const layerId = pushLayer();
    layerIdRef.current = layerId;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (hasLayerOnTop(layerId)) return; // 上面叠着弹框（如「自动更新设置」），Esc 先退它
      onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      popLayer(layerId);
      layerIdRef.current = null;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" aria-label="关闭数据更新" className="absolute inset-0 bg-ink/20 backdrop-blur-[1px]" onClick={onClose} />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="data-update-drawer-title"
        className="relative flex h-full w-full max-w-[26rem] flex-col border-l border-rule bg-paper-card shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-rule px-5 py-4">
          <div>
            <h2 id="data-update-drawer-title" className="text-lg font-semibold text-ink">数据更新</h2>
            <p className="mt-0.5 text-xs text-ink-muted">更新期间会暂停浏览，完成后自动恢复</p>
          </div>
          <button type="button" aria-label="关闭" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-md text-ink-muted hover:bg-paper-tint hover:text-ink">×</button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        <footer className="border-t border-rule p-4">
          <button type="button" onClick={onOpenScheduler} className="flex w-full items-center justify-between rounded-lg border border-rule-strong bg-paper-tint px-3 py-2.5 text-sm font-medium text-ink hover:border-info hover:text-info">
            <span>自动更新设置</span><span aria-hidden>›</span>
          </button>
        </footer>
      </aside>
    </div>,
    document.body,
  );
}
