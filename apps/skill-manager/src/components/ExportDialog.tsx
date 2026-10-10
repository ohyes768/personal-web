'use client';

import { useState } from 'react';
import {
  enabledExportTargets,
  exportTargetLabel,
  selectedExportTarget,
  type ExportTargetKey,
} from '@/lib/targets';
import type { ExportTarget, SkillCard } from '@/lib/types';

interface Props {
  skill: SkillCard;
  targets: ExportTarget[];
  targetsError: string;
  onManageTargets: () => void;
  busy: boolean;
  error: string;
  removing?: ExportTargetKey;
  initialTarget?: ExportTargetKey;
  onConfirm: (target: ExportTargetKey) => void;
  onClose: () => void;
}

export default function ExportDialog({
  skill,
  targets,
  targetsError,
  onManageTargets,
  busy,
  error,
  removing,
  initialTarget,
  onConfirm,
  onClose,
}: Props) {
  const [target, setTarget] = useState<ExportTargetKey>(initialTarget ?? '');
  const selected = selectedExportTarget(targets, target);
  const options = enabledExportTargets(targets);
  const canSubmit = Boolean(removing || (selected && !targetsError));
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={removing ? '清除导出记录' : '导出 Skill'}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
    >
      <form
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy && canSubmit) onConfirm(removing ?? selected);
        }}
      >
        <h2 className="text-lg font-semibold text-slate-800">
          {removing ? '清除导出记录' : '导出 Skill'} · {skill.name}
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          {removing
            ? `清除 ${exportTargetLabel(targets, removing)} 的台账记录，仅清除记录，不动本地已解压文件。`
            : '下载当前 Skill 的 ZIP，并记录本次版本。解压到所选工具的 skills 目录后即可使用。'}
        </p>
        {!removing ? (
          <fieldset
            disabled={busy || !!targetsError}
            className="mt-4 space-y-2"
          >
            <legend className="mb-2 text-sm font-medium">导出目标</legend>
            {options.map((item) => (
              <label
                key={item.id}
                className="flex items-start gap-2 rounded border border-slate-200 p-3 text-sm"
              >
                <input
                  type="radio"
                  name="export-target"
                  value={item.id}
                  checked={selected === item.id}
                  onChange={() => setTarget(item.id)}
                  className="mt-1"
                />
                <span className="min-w-0">
                  <span className="block break-all font-medium">{item.name}</span>
                  {item.install_path ? (
                    <span className="block break-all text-xs text-slate-500">
                      安装目录：{item.install_path}
                    </span>
                  ) : null}
                  {item.notes ? (
                    <span className="mt-1 block whitespace-pre-wrap break-all text-xs text-slate-500">
                      {item.notes}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
          </fieldset>
        ) : null}

        {!removing && (targetsError || !options.length) ? (
          <div className="mt-3 text-sm text-amber-700">
            <p role={targetsError ? 'alert' : 'status'}>
              {targetsError || '没有启用的导出目标，请先新增或启用目标。'}
            </p>
            <button
              type="button"
              onClick={onManageTargets}
              className="mt-2 underline"
            >
              管理导出目标
            </button>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="mt-3 text-sm text-rose-700">
            {error}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={busy || !canSubmit}
            className="rounded bg-sky-600 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? '处理中…' : removing ? '清除记录' : '下载 ZIP'}
          </button>
        </div>
      </form>
    </div>
  );
}
