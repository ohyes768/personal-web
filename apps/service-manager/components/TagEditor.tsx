"use client";

/** 标签编辑弹窗：勾选已有标签 + 输入新标签，整体替换保存。

 * 形态照搬 skill-manager 的 EditSkillTagsDialog；长度上限与后端一致（32）。
 */

import { useEffect, useRef, useState } from "react";
import { getTagCandidates } from "@/lib/tagCandidates";

const MAX_TAG_LENGTH = 32;

export function TagEditor({
  title,
  tags,
  allTags,
  busy = false,
  error,
  onSave,
  onClose,
}: {
  /** 弹窗标题里的对象名，例如服务名 */
  title: string;
  /** 本条当前标签 */
  tags: string[];
  /** 全库标签（候选来源） */
  allTags: string[];
  busy?: boolean;
  error?: string;
  onSave: (tags: string[]) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<string[]>(tags);
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  const candidates = getTagCandidates(allTags, tags, selected);

  function toggle(tag: string) {
    setSelected((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    );
  }

  function addDraft() {
    const tag = draft.trim();
    if (!tag) return;
    if (tag.length > MAX_TAG_LENGTH) {
      setDraftError(`标签最长 ${MAX_TAG_LENGTH} 个字符`);
      return;
    }
    if (selected.includes(tag)) {
      setDraftError("该标签已勾选");
      return;
    }
    setSelected((prev) => [...prev, tag]);
    setDraft("");
    setDraftError("");
  }

  return (
    <div className="dialog-backdrop">
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`编辑「${title}」的标签`}
      >
        <h2 className="dialog-title">编辑标签 · {title}</h2>

        {candidates.length > 0 ? (
          <div className="tag-candidates">
            {candidates.map((tag) => (
              <button
                key={tag}
                type="button"
                className={`tag-pill${selected.includes(tag) ? " active" : ""}`}
                aria-pressed={selected.includes(tag)}
                onClick={() => toggle(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
        ) : (
          <p className="small muted">还没有任何标签，在下面输入一个就能创建。</p>
        )}

        <div className="dialog-row">
          <input
            ref={inputRef}
            type="text"
            value={draft}
            maxLength={MAX_TAG_LENGTH}
            onChange={(event) => {
              setDraft(event.target.value);
              setDraftError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addDraft();
              }
            }}
            placeholder="输入新标签，回车添加"
            aria-label="新标签"
          />
          <button type="button" className="btn" onClick={addDraft} disabled={busy}>
            添加
          </button>
        </div>
        {draftError ? (
          <p className="small" style={{ color: "var(--bad)" }} role="alert">
            {draftError}
          </p>
        ) : null}

        {error ? (
          <p className="notice bad" role="alert">
            {error}
          </p>
        ) : null}

        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => onSave([...selected].sort())}
          >
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
