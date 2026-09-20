'use client';

import { useState, type FormEvent, type ReactNode } from 'react';

interface ConfirmActionDialogProps {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  busy?: boolean;
  error?: string;
  onConfirm: (password: string) => void;
  onCancel: () => void;
}

/**
 * 写操作密码确认弹窗（design 4.3），发布/登记/回滚/下架共用。
 *
 * 密码只存在于本组件 state：提交即清空、关闭即随组件卸载销毁，
 * 绝不写入 localStorage/sessionStorage（R5）。
 */
export default function ConfirmActionDialog({
  title,
  description,
  confirmLabel = '确认执行',
  busy = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmActionDialogProps) {
  const [password, setPassword] = useState('');

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!password || busy) {
      return;
    }
    const submitted = password;
    setPassword('');
    onConfirm(submitted);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <form
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
        onSubmit={handleSubmit}
      >
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        {description ? (
          <div className="mt-2 max-h-60 overflow-y-auto text-sm text-slate-600">
            {description}
          </div>
        ) : null}
        <label className="mt-4 block text-sm font-medium text-slate-700">
          管理密码
          <input
            type="password"
            value={password}
            autoFocus
            onChange={(event) => setPassword(event.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none disabled:bg-slate-100"
            placeholder="NAS 管理密码（不保存、不回显）"
          />
        </label>
        {error ? (
          <p className="mt-2 rounded bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={busy || password.length === 0}
            className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {busy ? '执行中…' : confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
