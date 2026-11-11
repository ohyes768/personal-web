"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, downloadBackup, type SummaryResponse } from "@/lib/api";
import { formatRelative } from "@/lib/status";
import SessionGate, { logout } from "@/components/SessionGate";
import { Toast } from "@/components/Widgets";

export default function SettingsPage() {
  return (
    <SessionGate>
      <SettingsView />
    </SessionGate>
  );
}

function SettingsView() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [preview, setPreview] = useState<{
    digest: string;
    registry_revision: number;
    counts: Record<string, number>;
    current_counts: Record<string, number>;
    warnings: string[];
  } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setSummary(await api.summary());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function exportNow() {
    try {
      const payload = await api.exportBackup();
      downloadBackup(payload);
      setToast("已导出人工台账 JSON");
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "导出失败");
    }
  }

  async function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] ?? null;
    setFile(chosen);
    setPreview(null);
    if (!chosen) return;
    setBusy(true);
    try {
      setPreview(await api.previewBackup(chosen));
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function restoreNow() {
    if (!file || !preview) return;
    if (
      !window.confirm(
        "确认用该文件替换当前人工台账？运行快照与检查结果会清空，恢复后可重新检查。",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const result = await api.restoreBackup(
        file,
        preview.digest,
        preview.registry_revision,
      );
      setToast(`已恢复：${result.restored.services} 个服务`);
      setPreview(null);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await load();
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "恢复失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>设置</h1>
      <p className="lead">数据导出与恢复、接入状态。系统凭据只在 NAS 环境变量里，网页不接收。</p>

      <h2>接入状态</h2>
      <div className="card">
        {summary ? (
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            <li>
              Docker 读取：
              <strong>{summary.docker_available ? "可用" : "不可用"}</strong>
              {summary.docker_error ? `（${summary.docker_error}）` : ""}
              <div className="muted">上次成功扫描：{formatRelative(summary.docker_last_success_at)}</div>
            </li>
            <li>
              检查循环心跳：
              <strong>{formatRelative(summary.checker_heartbeat)}</strong>
            </li>
            <li>
              台账版本号（registry_revision）：<span className="mono">{summary.registry_revision}</span>
            </li>
            <li>
              业务服务 {summary.services} 个 / 已关联组件 {summary.components} 个 / 未读发布{" "}
              {summary.unread_releases} 条
            </li>
          </ul>
        ) : (
          <p className="muted">加载中…</p>
        )}
        <p className="small muted" style={{ marginTop: 8 }}>
          检查周期由 NAS 环境变量决定（Docker 60 秒、URL 5 分钟、证书 12 小时、发布 6 小时）。
        </p>
      </div>

      <h2>导出</h2>
      <div className="card">
        <p className="small muted">
          导出只包含人工台账：服务、组件关联、入口、手工端口、仓库关联与忽略决定。
          不含运行快照、检查结果、历史任务、发布缓存与已读标记，也不含任何凭据。
        </p>
        <button className="btn" type="button" onClick={() => void exportNow()}>
          下载 JSON
        </button>
      </div>

      <h2>恢复</h2>
      <div className="card">
        <p className="small muted">
          先预览，再确认。恢复会替换人工台账并清空检查结果；不触发任何外部检查。
        </p>
        <div className="field">
          <label htmlFor="backup-file">选择 JSON 文件</label>
          <input
            id="backup-file"
            ref={inputRef}
            type="file"
            accept="application/json,.json"
            onChange={(event) => void pick(event)}
          />
        </div>
        {busy ? <p className="muted">处理中…</p> : null}
        {preview ? (
          <div className="card tight" style={{ background: "var(--bg)" }}>
            <h3 style={{ marginTop: 0 }}>预览</h3>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {Object.entries(preview.counts).map(([key, value]) => (
                <li key={key}>
                  {key}：文件 {value} 条 → 当前 {preview.current_counts[key] ?? 0} 条
                </li>
              ))}
            </ul>
            {preview.warnings.map((warning) => (
              <p className="notice" key={warning}>
                {warning}
              </p>
            ))}
            <div className="btn-row" style={{ marginTop: 8 }}>
              <button className="btn danger" type="button" onClick={() => void restoreNow()}>
                确认恢复
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setPreview(null);
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
              >
                取消
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <h2>会话</h2>
      <div className="card">
        <p className="small muted">会话有效期 12 小时，cookie 为 HttpOnly，页面不保存口令。</p>
        <button
          className="btn"
          type="button"
          onClick={async () => {
            await logout();
          }}
        >
          退出登录
        </button>
      </div>

      {error ? <p className="notice bad">{error}</p> : null}
      <Toast message={toast} />
    </>
  );
}
