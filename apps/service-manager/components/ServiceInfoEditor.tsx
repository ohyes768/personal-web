"use client";

/** 服务信息编辑弹窗：名称 + 用途 +（尚未登记时）主入口 URL。

 * 主入口已有值时**只读**——它是对外地址的事实，改它应该改反代配置，不是在台账里随手改。
 * 没登记过的服务可以在这里顺手填一个，填了就会纳入 URL / 证书检查。
 */

import { useEffect, useRef, useState } from "react";

export function ServiceInfoEditor({
  title,
  name,
  description,
  endpointUrl,
  busy = false,
  error,
  onSave,
  onClose,
}: {
  /** 弹窗标题里的对象名 */
  title: string;
  name: string;
  description: string;
  /** 已登记的主入口 URL；null 表示还没登记 */
  endpointUrl: string | null;
  busy?: boolean;
  error?: string;
  onSave: (values: { name: string; description: string; url: string | null }) => void;
  onClose: () => void;
}) {
  const [draftName, setDraftName] = useState(name);
  const [draftDescription, setDraftDescription] = useState(description);
  const [draftUrl, setDraftUrl] = useState(endpointUrl ?? "");
  const [urlError, setUrlError] = useState("");
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstField.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  function submit() {
    const trimmed = draftName.trim();
    if (!trimmed) {
      setUrlError("名称不能为空");
      return;
    }
    const url = draftUrl.trim();
    if (url && !/^https?:\/\//i.test(url)) {
      setUrlError("主入口要以 http:// 或 https:// 开头");
      return;
    }
    setUrlError("");
    onSave({
      name: trimmed,
      description: draftDescription,
      url: endpointUrl ? null : url || null,
    });
  }

  return (
    <div className="dialog-backdrop">
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`编辑「${title}」的信息`}
      >
        <h2 className="dialog-title">编辑 · {title}</h2>

        <div className="field">
          <label htmlFor="edit-name">名称</label>
          <input
            id="edit-name"
            ref={firstField}
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="edit-description">用途</label>
          <textarea
            id="edit-description"
            value={draftDescription}
            onChange={(event) => setDraftDescription(event.target.value)}
            placeholder="这条服务是干什么的，一句话说清"
          />
        </div>

        <div className="field">
          <label htmlFor="edit-endpoint">主入口 URL</label>
          <input
            id="edit-endpoint"
            value={draftUrl}
            onChange={(event) => setDraftUrl(event.target.value)}
            disabled={Boolean(endpointUrl)}
            placeholder="https://…（留空表示不登记）"
          />
          <span className="hint">
            {endpointUrl
              ? "已登记的主入口不在这里改——要换地址请改反代配置。"
              : "填了就会纳入 URL 与证书检查；留空表示这条服务没有对外入口。"}
          </span>
        </div>

        {urlError ? (
          <p className="small" style={{ color: "var(--bad)" }} role="alert">
            {urlError}
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
            onClick={submit}
          >
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
