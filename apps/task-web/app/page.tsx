"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend, statusColor, statusLabel, ProfileInfo, TaskView } from "@/lib/api";

const TARGET_LABELS: Record<string, { label: string; color: string }> = {
  dingtalk: { label: "钉钉", color: "#2563eb" },
  wechat: { label: "微信", color: "#16a34a" },
  rss: { label: "RSS", color: "#ea580c" },
  web: { label: "Web", color: "#0d9488" },
};

const GROUP_TABS: { key: "script" | "ai"; label: string }[] = [
  { key: "script", label: "脚本任务" },
  { key: "ai", label: "AI 任务" },
];

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskView[]>([]);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [error, setError] = useState("");
  const [pwdTarget, setPwdTarget] = useState<TaskView | null>(null);
  const [groupTab, setGroupTab] = useState<"script" | "ai">("script");

  const load = useCallback(async () => {
    try {
      const data = await apiGet<{ tasks: TaskView[] }>("/tasks");
      setTasks(data.tasks);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    load();
    apiGet<{ profiles: ProfileInfo[] }>("/profiles")
      .then((d) => setProfiles(d.profiles))
      .catch(() => {});
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  async function toggleEnabled(t: TaskView) {
    try {
      await apiSend("PUT", `/tasks/${t.id}/schedule`, { enabled: !t.enabled });
      load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function updateCron(t: TaskView, cron: string) {
    if (cron === t.cron) return;
    try {
      await apiSend("PUT", `/tasks/${t.id}/schedule`, { cron });
      load();
    } catch (e) {
      setError(String(e));
      load();
    }
  }

  async function updateProfile(t: TaskView, profile: string) {
    // `__reset__` = 清除覆盖，回到 tasks.yaml 登记推导值
    const next = profile === "__reset__" ? null : profile === "" ? null : profile;
    if (next === t.profile) return;
    try {
      await apiSend("PUT", `/tasks/${t.id}/profile`, { profile: next });
      load();
    } catch (e) {
      setError(String(e));
      load();
    }
  }

  async function manualRun(password: string) {
    if (!pwdTarget) return;
    try {
      await apiSend("POST", `/tasks/${pwdTarget.id}/run`, { password });
      setPwdTarget(null);
      setError("");
      setTimeout(load, 500);
    } catch (e) {
      setError(String(e));
    }
  }

  // 「涉及 Skill」「生效 Profile」列只在 AI 任务 tab 下出现（脚本任务没有这两个概念，避免整列都是「-」）
  const showAiCols = groupTab === "ai";

  return (
    <div>
      <div className="notice">
        结果含义：退出码 0 只代表进程正常退出，不代表业务投递（如钉钉推送）成功；
        「中断」含漏执行补记（不自动补跑，可手动触发）。
        <br />
        AI 任务的「生效 Profile」可在页面直接切换：执行时一并换掉凭证 env_file、HERMES_PROFILE
        与 jobs.json 来源，设置存库（不写 tasks.yaml，重新登记不会冲掉）。
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="filters" role="tablist">
        {GROUP_TABS.map((g) => (
          <button
            key={g.key}
            className="btn"
            style={groupTab === g.key
              ? { background: "#2563eb", color: "#fff", borderColor: "#2563eb" }
              : undefined}
            onClick={() => setGroupTab(g.key)}
          >
            {g.label}
            <span className="muted" style={{ marginLeft: 6, color: groupTab === g.key ? "#dbeafe" : undefined }}>
              {tasks.filter((t) => t.group === g.key).length}
            </span>
          </button>
        ))}
      </div>
      <table>
        <thead>
          <tr>
            <th>任务</th><th>输出</th>
            {showAiCols && <th>涉及 Skill</th>}
            {showAiCols && <th>生效 Profile（可切换）</th>}
            <th>说明</th><th>cron（可编辑）</th><th>启停</th>
            <th>上次执行</th><th>下次计划</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {tasks.filter((t) => t.group === groupTab).map((t) => (
            <tr key={t.id}>
              <td>
                <strong>{t.name}</strong>
                <span className="badge" style={{
                  background: t.group === "ai" ? "#7c3aed" : "#0284c7",
                  marginLeft: 6, fontSize: 11, verticalAlign: "middle",
                }}>
                  {t.group === "ai" ? "AI" : "脚本"}
                </span>
                <div className="mono muted">{t.id}</div>
                <div className="mono muted">{t.command}{t.cwd ? ` @ ${t.cwd}` : ""}</div>
              </td>
              <td>
                <div className="badge-stack">
                  {(t.targets || []).map((x) => (
                    <span key={x} className="badge" style={{
                      background: TARGET_LABELS[x]?.color ?? "#6b7280",
                    }}>
                      {TARGET_LABELS[x]?.label ?? x}
                    </span>
                  ))}
                  {(t.targets || []).length === 0 && (
                    <span className="muted" style={{ fontSize: 12 }}>待定</span>
                  )}
                </div>
              </td>
              {showAiCols && (
                <td style={{ maxWidth: 180 }}>
                  {(t.skills || []).length > 0 ? (
                    <div className="badge-stack">
                      {(t.skills || []).map((s) => (
                        <span key={s} className="badge badge-skill">{s}</span>
                      ))}
                    </div>
                  ) : (
                    <span className="muted" style={{ fontSize: 12 }}>无（纯 prompt）</span>
                  )}
                </td>
              )}
              {showAiCols && (
                <td>
                  <select
                    value={t.profile ?? ""}
                    style={{ width: 132 }}
                    title="切换后立即生效：执行时同时换凭证 env_file、HERMES_PROFILE 和 jobs.json 来源"
                    onChange={(e) => updateProfile(t, e.target.value)}
                  >
                    {!t.profile && <option value="">按登记（未知）</option>}
                    {t.profile && !profiles.some((p) => p.name === t.profile) && (
                      <option value={t.profile}>{t.profile}（目录外）</option>
                    )}
                    {profiles.map((p) => (
                      <option key={p.name} value={p.name}>{p.name}</option>
                    ))}
                    {t.profile_source === "override" && (
                      <option value="__reset__">↩ 回到登记值</option>
                    )}
                  </select>
                  {t.profile_source === "override" ? (
                    <div className="muted" style={{ fontSize: 11 }}>已覆盖登记值</div>
                  ) : (
                    <div className="muted" style={{ fontSize: 11 }}>来自 tasks.yaml</div>
                  )}
                </td>
              )}
              <td className="muted" style={{ maxWidth: 220 }}>{t.description}</td>
              <td>
                <input
                  className="mono" defaultValue={t.cron} style={{ width: 110 }}
                  onBlur={(e) => updateCron(t, e.target.value.trim())}
                />
                <div className="muted">超时 {t.timeout_seconds}s</div>
              </td>
              <td>
                <button className="btn" onClick={() => toggleEnabled(t)}>
                  {t.enabled ? "暂停" : "启用"}
                </button>
                <div className="badge" style={{ background: t.enabled ? "#16a34a" : "#6b7280", marginTop: 4 }}>
                  {t.enabled ? "已启用" : "已禁用"}
                </div>
              </td>
              <td>
                {t.last_run ? (
                  <>
                    <span className="badge" style={{ background: statusColor(t.last_run.status) }}>
                      {statusLabel(t.last_run.status)}
                    </span>
                    <div className="muted">{t.last_run.started_at || t.last_run.scheduled_at || "-"}</div>
                    {t.last_run.missed_schedule_at && (
                      <div className="muted">漏执行：{t.last_run.missed_schedule_at}</div>
                    )}
                  </>
                ) : <span className="muted">从未执行</span>}
              </td>
              <td className="muted">{t.next_fire_time || "-"}</td>
              <td>
                <button className="btn btn-primary" onClick={() => setPwdTarget(t)}>立即执行</button>
                <div style={{ marginTop: 4 }}>
                  <Link href={`/runs?task_id=${t.id}`} className="muted">运行记录 →</Link>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {pwdTarget && (
        <PasswordDialog
          taskName={pwdTarget.name}
          onCancel={() => setPwdTarget(null)}
          onSubmit={manualRun}
        />
      )}
    </div>
  );
}

function PasswordDialog({ taskName, onCancel, onSubmit }: {
  taskName: string;
  onCancel: () => void;
  onSubmit: (password: string) => void;
}) {
  const [pwd, setPwd] = useState("");
  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>手动执行「{taskName}」</h3>
        <p className="muted">该操作会真实执行任务命令，请输入管理密码确认。</p>
        <input
          type="password" autoFocus value={pwd}
          placeholder="管理密码"
          onChange={(e) => setPwd(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSubmit(pwd)}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onCancel}>取消</button>
          <button className="btn btn-primary" onClick={() => onSubmit(pwd)}>确认执行</button>
        </div>
      </div>
    </div>
  );
}
