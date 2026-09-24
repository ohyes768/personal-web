'use client';

import { useState, type FormEvent } from 'react';
import ConfirmActionDialog from '@/components/ConfirmActionDialog';
import type { SkillCard } from '@/lib/types';

const MAX_TAG_LENGTH = 40;

interface EditSkillTagsDialogProps {
  skill: SkillCard;
  allTags: string[];
  busy?: boolean;
  error?: string;
  /** 保存 = 该 skill 标签的全量替换；密码只随本次请求传输 */
  onSave: (tags: string[], password: string) => void;
  onClose: () => void;
}

/**
 * 单卡标签编辑弹窗：勾选已有标签 + 输入新标签，保存时经
 * ConfirmActionDialog 输入管理密码（密码不落盘，R5）。
 */
export default function EditSkillTagsDialog({
  skill,
  allTags,
  busy = false,
  error,
  onSave,
  onClose,
}: EditSkillTagsDialogProps) {
  const [selected, setSelected] = useState<string[]>(skill.tags);
  const [draft, setDraft] = useState('');
  const [draftError, setDraftError] = useState('');
  const [confirming, setConfirming] = useState(false);

  // 候选全集 = 全局已有标签 ∪ 该 skill 现有标签，排序去重
  const candidates = Array.from(new Set([...allTags, ...skill.tags])).sort();

  function toggle(tag: string) {
    setSelected((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }

  function addDraft() {
    const tag = draft.trim();
    if (!tag) {
      return;
    }
    if (tag.length > MAX_TAG_LENGTH) {
      setDraftError(`标签最长 ${MAX_TAG_LENGTH} 个字符`);
      return;
    }
    if (selected.includes(tag)) {
      setDraftError('该标签已勾选');
      return;
    }
    setSelected((prev) => [...prev, tag]);
    setDraft('');
    setDraftError('');
  }

  function handleDraftKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      addDraft();
    }
  }

  function handleSave(event: FormEvent) {
    event.preventDefault();
    if (busy) {
      return;
    }
    setConfirming(true);
  }

  if (confirming) {
    return (
      <ConfirmActionDialog
        title="保存标签"
        description={
          <p>
            将把「{skill.name}」的标签保存为：
            {selected.length > 0 ? (
              <span className="font-medium">{[...selected].sort().join('、')}</span>
            ) : (
              <span className="font-medium">（清空全部标签）</span>
            )}
          </p>
        }
        confirmLabel="保存"
        busy={busy}
        error={error}
        onConfirm={(password) => onSave([...selected].sort(), password)}
        onCancel={() => setConfirming(false)}
      />
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`编辑「${skill.name}」的标签`}
    >
      <form
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
        onSubmit={handleSave}
      >
        <h2 className="text-lg font-semibold text-slate-800">
          编辑标签 · {skill.name}
        </h2>

        {candidates.length > 0 ? (
          <div className="mt-3 flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
            {candidates.map((tag) => {
              const active = selected.includes(tag);
              return (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggle(tag)}
                  className={`rounded-full px-2.5 py-0.5 text-xs ${
                    active
                      ? 'bg-sky-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {tag}
                </button>
              );
            })}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-400">暂无任何标签，输入新标签创建</p>
        )}

        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={draft}
            maxLength={MAX_TAG_LENGTH}
            onChange={(event) => {
              setDraft(event.target.value);
              setDraftError('');
            }}
            onKeyDown={handleDraftKeyDown}
            placeholder="输入新标签，回车添加"
            className="flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={addDraft}
            disabled={!draft.trim()}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            添加
          </button>
        </div>
        {draftError ? (
          <p className="mt-1.5 text-xs text-rose-600" role="alert">
            {draftError}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-50"
          >
            保存
          </button>
        </div>
      </form>
    </div>
  );
}
