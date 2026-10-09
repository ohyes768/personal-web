'use client';
import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
export function RelayDialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); }
      if (event.key !== 'Tab') return;
      const elements = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex="0"]') || []).filter(element => element.getClientRects().length > 0);
      const first = elements[0], last = elements[elements.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === ref.current)) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return createPortal(<div className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md p-3 sm:p-6 flex items-center justify-center" onClick={onClose}>
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="bg-paper-card rounded-xl shadow-2xl w-full max-w-[680px] max-h-[90dvh] flex flex-col outline-none" onClick={e => e.stopPropagation()}>
      <header className="flex items-center justify-between gap-3 px-5 sm:px-7 py-5 border-b border-rule"><h2 className="font-serif-cn text-xl font-bold text-ink-strong">{title}</h2><button onClick={onClose} aria-label="关闭" className="text-ink-muted rounded px-3 py-1 hover:bg-paper-deep">✕</button></header>
      <div className="overflow-y-auto p-5 sm:p-7 font-ui text-sm text-ink">{children}</div>
    </div>
  </div>, document.body);
}
