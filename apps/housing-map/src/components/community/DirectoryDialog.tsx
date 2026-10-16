'use client';

import { useEffect, useRef, type ReactNode } from 'react';

/** 名单详情共用弹窗；原生 dialog 管理焦点约束及关闭后的焦点恢复。 */
export default function DirectoryDialog({ title, onClose, children }: {
  title: string; onClose: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      element?.close();
      document.body.style.overflow = overflow;
    };
  }, []);
  return <dialog ref={dialog} className="directory-detail directory-detail-dialog" aria-label={title}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="directory-source-heading directory-dialog-heading"><h3>{title}</h3>
      <button autoFocus type="button" className="btn btn-secondary" onClick={onClose}>关闭</button></div>
    <div className="directory-dialog-content">{children}</div>
  </dialog>;
}
