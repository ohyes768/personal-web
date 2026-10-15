'use client';

import { useState } from 'react';
import {
  createExportTarget,
  deleteExportTarget,
  updateExportTarget,
} from '@/lib/api';
import type { ExportTarget, ExportTargetInput } from '@/lib/types';
import { EXPORT_TARGET_ID_PATTERN } from '@/lib/targets';
import {
  dialogGhostButton,
  dialogPrimaryButton,
  emptyStateClass,
  errorBlockClass,
  ghostButton,
  cardClass,
  inputClass,
  primaryButton,
} from '@/lib/ui';
import ConfirmActionDialog from './ConfirmActionDialog';
import type { Notice } from './SourceWorkspace';

interface Props {
  targets: ExportTarget[];
  loading: boolean;
  error: string;
  onRefresh: () => Promise<void>;
  onNotify?: (notice: Notice) => void;
  /** 删除被导出记录拦截时，跳回管理看板清除记录。 */
  onManage: () => void;
}
const empty: ExportTargetInput = {
  id: '',
  name: '',
  install_path: '',
  notes: '',
  enabled: true,
};

export default function ExportTargetManager({
  targets,
  loading,
  error,
  onRefresh,
  onNotify,
  onManage,
}: Props) {
  const [editing, setEditing] = useState<ExportTarget | 'new' | null>(null);
  const [form, setForm] = useState<ExportTargetInput>(empty);
  const [deleting, setDeleting] = useState<ExportTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  function openEditor(target: ExportTarget | 'new') {
    setActionError('');
    setEditing(target);
    setForm(
      target === 'new'
        ? { ...empty }
        : {
            id: target.id,
            name: target.name,
            install_path: target.install_path,
            notes: target.notes,
            enabled: target.enabled,
          }
    );
  }
  async function save() {
    setBusy(true);
    setActionError('');
    try {
      if (editing === 'new') await createExportTarget(form);
      else if (editing) {
        const { id, ...fields } = form;
        await updateExportTarget(id, fields);
      }
      setEditing(null);
      onNotify?.({ kind: 'ok', text: `已保存目标「${form.name}」` });
      await onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '保存目标失败');
    } finally {
      setBusy(false);
    }
  }
  async function toggle(target: ExportTarget) {
    setBusy(true);
    setActionError('');
    try {
      await updateExportTarget(target.id, { enabled: !target.enabled });
      onNotify?.({
        kind: 'ok',
        text: `${target.enabled ? '已停用' : '已启用'}目标「${target.name}」`,
      });
      await onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '更新目标失败');
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!deleting) return;
    setBusy(true);
    setActionError('');
    try {
      await deleteExportTarget(deleting.id);
      setDeleting(null);
      onNotify?.({ kind: 'ok', text: `已删除目标「${deleting.name}」` });
      await onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '删除目标失败');
    } finally {
      setBusy(false);
    }
  }
  function closeDelete() {
    if (!busy) {
      setDeleting(null);
      setActionError('');
    }
  }
  return (
    <section className="min-h-0 flex-1 overflow-y-auto pb-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">导出目标</h2>
          <p className="mt-1 text-sm text-slate-500">
            为工具或设备保存 ZIP
            安装说明，下载后手动解压。目录说明不会自动写入文件。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy || loading}
            onClick={() => void onRefresh()}
            className={ghostButton}
          >
            刷新
          </button>
          <button
            type="button"
            disabled={busy || loading || !!error}
            onClick={() => openEditor('new')}
            className={primaryButton}
          >
            新增目标
          </button>
        </div>
      </div>
      {error ? (
        <p
          role="alert"
          className={`mb-3 ${errorBlockClass} flex flex-wrap items-center justify-between gap-2`}
        >
          <span>{error}</span>
          <button
            type="button"
            className={ghostButton}
            onClick={() => void onRefresh()}
          >
            重试
          </button>
        </p>
      ) : null}

      {actionError && !editing && !deleting ? (
        <p role="alert" className={`mb-3 ${errorBlockClass}`}>
          {actionError}
        </p>
      ) : null}

      {loading ? (
        <p className="p-6 text-center text-sm text-slate-500">加载中…</p>
      ) : !targets.length && !error ? (
        <div className={emptyStateClass}>
          <p className="text-slate-600">还没有导出目标</p>
          <p className="mt-1 text-sm text-slate-500">
            新增一个工具或设备，即可在 Skill 卡片下载对应 ZIP。
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {targets.map((target) => (
            <li key={target.id} className={cardClass}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="min-w-0 break-all font-medium text-slate-800">
                      {target.name}
                    </h3>
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${target.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}
                    >
                      {target.enabled ? '已启用' : '已停用'}
                    </span>
                  </div>
                  <p className="mt-1 break-all font-mono text-xs text-slate-500">
                    {target.id}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy || !!error}
                    onClick={() => openEditor(target)}
                    className={ghostButton}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    disabled={busy || !!error}
                    onClick={() => void toggle(target)}
                    className={ghostButton}
                  >
                    {target.enabled ? '停用' : '启用'}
                  </button>
                  <button
                    type="button"
                    disabled={busy || !!error}
                    onClick={() => {
                      setActionError('');
                      setDeleting(target);
                    }}
                    className={`${ghostButton} text-rose-700`}
                  >
                    删除
                  </button>
                </div>
              </div>
              <p className="mt-3 break-all text-sm text-slate-600">
                安装目录：
                <span className="font-mono">
                  {target.install_path || '未填写'}
                </span>
              </p>
              {target.notes ? (
                <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-500">
                  {target.notes}
                </p>
              ) : null}
              <p className="mt-3 text-xs text-slate-500">
                {target.deployment_count} 条导出记录
                {!target.enabled ? ' · 历史记录可在 Skill 卡片清除' : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
      {editing ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={editing === 'new' ? '新增导出目标' : '编辑导出目标'}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy) void save();
            }}
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
          >
            <h2 className="text-lg font-semibold text-slate-800">
              {editing === 'new' ? '新增' : '编辑'}导出目标
            </h2>
            <fieldset disabled={busy} className="mt-4 space-y-3">
              <label className="block text-sm text-slate-600">
                目标 ID
                <input
                  required
                  pattern={EXPORT_TARGET_ID_PATTERN}
                  maxLength={63}
                  disabled={editing !== 'new'}
                  value={form.id}
                  onChange={(event) =>
                    setForm({ ...form, id: event.target.value })
                  }
                  placeholder="例如 laptop-codex"
                  className={`${inputClass} disabled:bg-slate-50`}
                />
                <span className="mt-1 block text-xs text-slate-500">
                  小写字母、数字和短横线，创建后不可修改。
                </span>
              </label>
              <label className="block text-sm text-slate-600">
                名称
                <input
                  required
                  maxLength={100}
                  value={form.name}
                  onChange={(event) =>
                    setForm({ ...form, name: event.target.value })
                  }
                  placeholder="例如 工作笔记本 Codex"
                  className={inputClass}
                />
              </label>
              <label className="block text-sm text-slate-600">
                安装目录说明
                <input
                  maxLength={500}
                  value={form.install_path}
                  onChange={(event) =>
                    setForm({ ...form, install_path: event.target.value })
                  }
                  placeholder="例如 ~/.codex/skills"
                  className={inputClass}
                />
              </label>
              <label className="block text-sm text-slate-600">
                备注
                <textarea
                  maxLength={2000}
                  rows={3}
                  value={form.notes}
                  onChange={(event) =>
                    setForm({ ...form, notes: event.target.value })
                  }
                  className={inputClass}
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) =>
                    setForm({ ...form, enabled: event.target.checked })
                  }
                />
                启用此目标
              </label>
            </fieldset>
            {actionError ? (
              <p
                role="alert"
                className="mt-3 rounded bg-rose-50 px-3 py-2 text-sm text-rose-700"
              >
                {actionError}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditing(null)}
                className={dialogGhostButton}
              >
                取消
              </button>
              <button type="submit" disabled={busy} className={dialogPrimaryButton}>
                {busy ? '保存中…' : '保存'}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {deleting ? (
        <ConfirmActionDialog
          title={`删除「${deleting.name}」？`}
          description={
            deleting.deployment_count ? (
              <div className="space-y-2">
                <p>
                  仍有 {deleting.deployment_count}{' '}
                  条导出记录，请先到 Skill 卡片清除记录后再删除。
                </p>
                <button
                  type="button"
                  className={ghostButton}
                  onClick={() => {
                    closeDelete();
                    onManage();
                  }}
                >
                  到管理看板清除记录
                </button>
              </div>
            ) : (
              <p>删除目标配置。已下载的 ZIP 和解压文件不受影响。</p>
            )
          }
          requirePassword={false}
          danger
          confirmLabel="删除"
          busy={busy}
          error={actionError}
          completed={deleting.deployment_count > 0}
          onCancel={closeDelete}
          onConfirm={() => void remove()}
        />
      ) : null}
    </section>
  );
}
