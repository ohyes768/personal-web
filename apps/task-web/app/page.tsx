"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend, statusColor, statusLabel, ProfileInfo, TaskView } from "@/lib/api";
import { fmtTime } from "@/lib/time";
import { taskDisplayName } from "@/lib/name";

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

/** cron 粗校验：5 个空白分隔的字段（精确校验由后端负责，这里挡住手滑） */
const CRON_RE = /^(\S+\s+){4}\S+$/;

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskView[]>([]);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [error, setError] = useState("");
  const [pwdTarget, setPwdTarget] = useState<TaskView | null>(null);
  const [groupTab, setGroupTab] = useState<"script" | "ai">("script");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<{ tasks: TaskView[] }>("/tasks");
      setTasks(data.tasks);
      setLastRefresh(new Date());
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
  const stale = lastRefresh != null && Date.now() - lastRefresh.getTime() > 15000;

  // 按下次执行时间升序：第一行就是马上要执行的任务；已禁用（无下次时间）沉底
  const groupTasks = tasks
    .filter((t) => t.group === groupTab)
    .sort((a, b) => {
      const ka = a.enabled && a.next_fire_time ? a.next_fire_time : "9999";
      const kb = b.enabled && b.next_fire_time ? b.next_fire_time : "9999";
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  const nextUpId = groupTasks[0]?.enabled ? groupTasks[0].id : null;

  return (
    <div>
      <details className="notice">
        <summary>状态含义说明 <span className="muted">（退出码 0 ≠ 业务投递成功；中断含漏执行补记；AI 任务 Profile 可直接切换）</span></summary>
        <div style={{ marginTop: 6 }}>
          结果含义：退出码 0 只代表进程正常退出，不代表业务投递（如钉钉推送）成功；
          「中断」含漏执行补记（不自动补跑，可手动触发）。
          <br />
          AI 任务的「生效 Profile」可在页面直接切换：执行时一并换掉凭证 env_file、HERMES_PROFILE
          与 jobs.json 来源，设置存库（不写 tasks.yaml，重新登记不会冲掉）。
        </div>
      </details>
      {error && <p className="error-text">{error}</p>}
      <div className="filters" role="tablist">
        {GROUP_TABS.map((g) => (
          <button
            key={g.key}
            className={`btn${groupTab === g.key ? " tab-active" : ""}`}
            onClick={() => setGroupTab(g.key)}
          >
            {g.label}
            <span className="muted" style={{ marginLeft: 6 }}>
              {tasks.filter((t) => t.group === g.key).length}
            </span>
          </button>
        ))}
        <span className={`refresh-chip${stale ? " stale" : ""}`} title="每 5 秒自动刷新">
          {lastRefresh ? `上次刷新 ${fmtTime(lastRefresh.toISOString())} · 自动` : "加载中…"}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>任务</th><th>输出</th>
            {showAiCols && <th>涉及 Skill</th>}
            {showAiCols && <th>生效 Profile（可切换）</th>}
            <th>cron（可编辑）</th><th>启停</th>
            <th>上次执行</th><th>下次计划</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {groupTasks.map((t) => {
            const missed = t.last_run?.missed_schedule_at;
            const isNextUp = t.id === nextUpId;
            return (
              <tr key={t.id} className={isNextUp ? "row-next-up" : undefined}>
                <td>
                  <strong title={t.description}>{taskDisplayName(t.name)}</strong>
                  {isNextUp && (
                    <span className="badge" style={{ background: "#ea580c", marginLeft: 6, verticalAlign: "middle" }}
                      title="这是下一个即将执行的任务">
                      即将执行
                    </span>
                  )}
                  <span className="badge" style={{
                    background: t.group === "ai" ? "#7c3aed" : "#0284c7",
                    marginLeft: 6, verticalAlign: "middle",
                  }}>
                    {t.group === "ai" ? "AI" : "脚本"}
                  </span>
                  <div className="mono muted truncate" title={t.id}>
                    {t.id}
                  </div>
                </td>
                <td>
                  {(t.targets || []).map((x) => (
                    <span key={x} className="badge" style={{
                      background: TARGET_LABELS[x]?.color ?? "#6b7280", marginRight: 4,
                    }}>
                      {TARGET_LABELS[x]?.label ?? x}
                    </span>
                  ))}
                  {(t.targets || []).length === 0 && (
                    <span className="muted" style={{ fontSize: 12 }}>待定</span>
                  )}
                </td>
                {showAiCols && (
                  <td style={{ maxWidth: 180 }}>
                    {(t.skills || []).length > 0 ? (
                      <span className="badge-stack">
                        {(t.skills || []).map((s) => (
                          // 同域直跳 skill 管理台（nginx 下 /skills），?q= 打开即过滤出该 skill
                          <a key={s} className="badge badge-skill" style={{ color: "#9d174d", textDecoration: "none" }}
                            href={`/skills/?q=${encodeURIComponent(s)}`} target="_blank" rel="noreferrer"
                            title={`在 Skill 管理台查看 ${s}`}
                          >{s}</a>
                        ))}
                      </span>
                    ) : (
                      <span className="muted" style={{ fontSize: 12 }}>无（纯 prompt）</span>
                    )}
                  </td>
                )}
                {showAiCols && (
                  <td>
                    <ProfileCell task={t} profiles={profiles} onChanged={load} onError={setError} />
                  </td>
                )}
                <td>
                  <CronCell task={t} onChanged={load} onError={setError} />
                </td>
                <td>
                  <button
                    className="btn"
                    title={t.enabled ? "点击暂停该任务" : "点击启用该任务"}
                    onClick={() => toggleEnabled(t)}
                  >
                    {t.enabled ? "暂停" : "启用"}
                  </button>
                </td>
                <td>
                  {t.last_run ? (
                    <>
                      <span
                        className="badge"
                        style={{ background: statusColor(t.last_run.status) }}
                        title={`${statusLabel(t.last_run.status)}\n${t.last_run.started_at || t.last_run.scheduled_at || "-"}${missed ? `\n漏执行：${missed}` : ""}`}
                      >
                        {statusLabel(t.last_run.status)}
                      </span>
                      <span className="muted" style={{ marginLeft: 4 }}>
                        {fmtTime(t.last_run.started_at || t.last_run.scheduled_at)}
                      </span>
                      {missed && <span style={{ color: "#7c3aed", fontSize: 11, marginLeft: 4 }}>漏</span>}
                    </>
                  ) : <span className="muted">从未执行</span>}
                </td>
                <td className="muted" title={t.next_fire_time || undefined}>
                  {t.next_fire_time ? fmtTime(t.next_fire_time) : "-"}
                </td>
                <td>
                  <span className="cell-actions">
                    <button className="btn btn-primary" onClick={() => setPwdTarget(t)}>立即执行</button>
                    <Link href={`/runs?task_id=${t.id}`} className="muted" title="查看该任务的运行记录">记录</Link>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {pwdTarget && (
        <PasswordDialog
          taskName={taskDisplayName(pwdTarget.name)}
          onCancel={() => setPwdTarget(null)}
          onSubmit={manualRun}
        />
      )}
    </div>
  );
}

/** cron 单元格：脏值保护——失焦不提交，出现「保存/撤销」，点保存且格式合法才提交 */
function CronCell({ task, onChanged, onError }: {
  task: TaskView;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? task.cron;
  const dirty = draft !== null && draft.trim() !== task.cron;
  const invalid = dirty && !CRON_RE.test(value.trim());

  async function save() {
    if (draft === null) return;
    const cron = draft.trim();
    if (!CRON_RE.test(cron)) return;
    setDraft(null);
    if (cron === task.cron) return;
    try {
      await apiSend("PUT", `/tasks/${task.id}/schedule`, { cron });
      onChanged();
    } catch (e) {
      onError(String(e));
      setDraft(cron);
    }
  }

  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <input
        className={`mono${invalid ? " input-invalid" : ""}`}
        value={value}
        style={{ width: 110 }}
        title={`超时 ${task.timeout_seconds}s；修改后需点「存」才生效`}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") setDraft(null);
        }}
      />
      <span className="muted" style={{ fontSize: 11, marginLeft: 4 }}>{task.timeout_seconds}s</span>
      {dirty && (
        <span className="dirty-actions">
          <button className="btn btn-mini save" disabled={invalid} title={invalid ? "cron 需为 5 个空格分隔字段" : "保存修改"}
            onClick={save}>存</button>
          <button className="btn btn-mini" title="放弃修改" onClick={() => setDraft(null)}>撤</button>
        </span>
      )}
    </span>
  );
}

/** Profile 单元格：下拉改动不立即生效，出现「保存/撤销」，点保存才提交 */
function ProfileCell({ task, profiles, onChanged, onError }: {
  task: TaskView;
  profiles: ProfileInfo[];
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? task.profile ?? "";
  const dirty = draft !== null && draft !== (task.profile ?? "");

  async function save() {
    if (draft === null) return;
    // `__reset__` = 清除覆盖，回到 tasks.yaml 登记推导值
    const next = draft === "__reset__" || draft === "" ? null : draft;
    setDraft(null);
    if (next === task.profile) return;
    try {
      await apiSend("PUT", `/tasks/${task.id}/profile`, { profile: next });
      onChanged();
    } catch (e) {
      onError(String(e));
      setDraft(draft);
    }
  }

  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <select
        value={value}
        style={{ width: 132 }}
        title="切换后保存即生效：执行时同时换凭证 env_file、HERMES_PROFILE 和 jobs.json 来源"
        onChange={(e) => setDraft(e.target.value)}
      >
        {!task.profile && <option value="">按登记（未知）</option>}
        {task.profile && !profiles.some((p) => p.name === task.profile) && (
          <option value={task.profile}>{task.profile}（目录外）</option>
        )}
        {profiles.map((p) => (
          <option key={p.name} value={p.name}>{p.name}</option>
        ))}
        {task.profile_source === "override" && (
          <option value="__reset__">↩ 回到登记值</option>
        )}
      </select>
      <span className="muted" style={{ fontSize: 11, marginLeft: 4 }}>
        {task.profile_source === "override" ? "已覆盖" : "登记"}
      </span>
      {dirty && (
        <span className="dirty-actions">
          <button className="btn btn-mini save" title="保存修改" onClick={save}>存</button>
          <button className="btn btn-mini" title="放弃修改" onClick={() => setDraft(null)}>撤</button>
        </span>
      )}
    </span>
  );
}

function PasswordDialog({ taskName, onCancel, onSubmit }: {
  taskName: string;
  onCancel: () => void;
  onSubmit: (password: string) => void;
}) {
  const [pwd, setPwd] = useState("");
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onCancel]);
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
