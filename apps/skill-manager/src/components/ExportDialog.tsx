'use client';

import { useState } from 'react';
import { EXPORT_TARGETS, TARGET_LABEL, type ExportTargetKey } from '@/lib/targets';
import type { SkillCard } from '@/lib/types';

interface Props {
  skill: SkillCard;
  busy: boolean;
  error: string;
  removing?: ExportTargetKey;
  initialTarget?: ExportTargetKey;
  onConfirm: (target: ExportTargetKey) => void;
  onClose: () => void;
}

export default function ExportDialog({ skill, busy, error, removing, initialTarget = 'windows-codex', onConfirm, onClose }: Props) {
  const [target, setTarget] = useState<ExportTargetKey>(initialTarget);
  return (
    <div role="dialog" aria-modal="true" aria-label={removing ? '清除导出记录' : '导出 Skill'} className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl" onSubmit={(event) => { event.preventDefault(); if (!busy) onConfirm(removing ?? target); }}>
        <h2 className="text-lg font-semibold text-slate-800">{removing ? '清除导出记录' : '导出 Skill'} · {skill.name}</h2>
        <p className="mt-2 text-sm text-slate-600">{removing ? `清除 ${TARGET_LABEL[removing]} 的台账记录，仅清除记录，不动本地已解压文件。` : '下载当前 Skill 的 ZIP，并记录本次版本。解压到所选工具的 skills 目录后即可使用。'}</p>
        {!removing ? <fieldset disabled={busy} className="mt-4 space-y-2"><legend className="mb-2 text-sm font-medium">导出目标</legend>{EXPORT_TARGETS.map((key) => <label key={key} className="flex items-center gap-2 rounded border border-slate-200 p-3 text-sm"><input type="radio" name="export-target" value={key} checked={target === key} onChange={() => setTarget(key)} />{TARGET_LABEL[key]}</label>)}</fieldset> : null}
        {error ? <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p> : null}
        <div className="mt-4 flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose} className="rounded border border-slate-300 px-3 py-2 text-sm">取消</button><button type="submit" disabled={busy} className="rounded bg-sky-600 px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '处理中…' : removing ? '清除记录' : '下载 ZIP'}</button></div>
      </form>
    </div>
  );
}
