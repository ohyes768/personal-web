'use client';

import { useState, type FormEvent, type ReactNode } from 'react';
import {
  dialogDangerButton,
  dialogGhostButton,
  dialogPrimaryButton,
} from '@/lib/ui';

interface ConfirmActionDialogProps {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  /** 确认按钮使用 rose-600 实心（不可逆动作）；默认 sky。 */
  danger?: boolean;
  /** 是否要求管理密码（默认 true）。安装目标等写 NAS 操作必须保留密码。 */
  requirePassword?: boolean;
  busy?: boolean;
  error?: string;
  completed?: boolean;
  /** completed 展示态下关闭按钮的文案。 */
  completedLabel?: string;
  onConfirm: (password: string) => void;
  onCancel: () => void;
}

/**
 * 写操作确认弹窗（design 4.3），发布/登记/回滚/下架/目标管理共用。
 *
 * 密码只存在于本组件 state：提交即清空、关闭即随组件卸载销毁，
 * 绝不写入 localStorage/sessionStorage（R5）。
 * requirePassword={false} 的变体供无破坏面的本地台账操作（如导出目标）使用。
 */
export default function ConfirmActionDialog({
  title,
  description,
  confirmLabel = '确认执行',
  danger = false,
  requirePassword = true,
  busy = false,
  error,
  completed = false,
  completedLabel = '知道了',
  onConfirm,
  onCancel,
}: ConfirmActionDialogProps) {
  const [password, setPassword] = useState('');

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy || (requirePassword && !password)) {
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
        {!completed && requirePassword ? (
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
        ) : null}
        {error ? (
          <p
            className="mt-2 rounded bg-rose-50 px-3 py-2 text-sm text-rose-700"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className={dialogGhostButton}
          >
            {completed ? completedLabel : '取消'}
          </button>
          {!completed ? (
            <button
              type="submit"
              disabled={busy || (requirePassword && password.length === 0)}
              className={danger ? dialogDangerButton : dialogPrimaryButton}
            >
              {busy ? '执行中…' : confirmLabel}
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
