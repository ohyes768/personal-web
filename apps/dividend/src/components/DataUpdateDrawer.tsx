'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';

interface DataUpdateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenScheduler: () => void;
  children: React.ReactNode;
}

export function DataUpdateDrawer({ isOpen, onClose, onOpenScheduler, children }: DataUpdateDrawerProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" aria-label="关闭数据更新" className="absolute inset-0 bg-ink/20 backdrop-blur-[1px]" onClick={onClose} />
      <aside role="complementary" aria-label="数据更新" className="relative flex h-full w-full max-w-[26rem] flex-col border-l border-rule bg-paper-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-rule px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-ink">数据更新</h2>
            <p className="mt-0.5 text-xs text-ink-muted">更新不会中断当前筛选和浏览</p>
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
