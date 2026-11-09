"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiGet, Run, statusColor, statusLabel } from "@/lib/api";
import { fmtTime } from "@/lib/time";
import { taskDisplayName } from "@/lib/name";

const STATUS_OPTIONS = ["", "waiting", "running", "success", "failed", "timeout", "interrupted", "skipped"];

function RunsInner() {
  const sp = useSearchParams();
  const [taskId, setTaskId] = useState(sp.get("task_id") || "");
  const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [tasks, setTasks] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (taskId) params.set("task_id", taskId);
      if (status) params.set("status", status);
      const data = await apiGet<{ runs: Run[] }>(`/runs?${params}`);
      // 计划时间倒序 + 可选按日期前缀过滤（后端不支持日期参数时兜底）
      const filtered = date
        ? data.runs.filter((r) => (r.scheduled_at || r.started_at || "").startsWith(date))
        : data.runs;
      filtered.sort((a, b) =>
        (b.scheduled_at || b.started_at || "").localeCompare(a.scheduled_at || a.started_at || ""));
      setRuns(filtered);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, [taskId, status, date]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  // 任务下拉：避免手填 task_id（识别优先于回忆）
  useEffect(() => {
    apiGet<{ tasks: { id: string; name: string }[] }>("/tasks")
      .then((d) => setTasks(d.tasks))
      .catch(() => {});
  }, []);

  return (
    <div>
      <div className="filters">
        <select value={taskId} onChange={(e) => setTaskId(e.target.value)} title="选择任务">
          <option value="">全部任务</option>
          {tasks.map((t) => (
            <option key={t.id} value={t.id}>{taskDisplayName(t.name)}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s ? statusLabel(s) : "全部状态"}</option>
          ))}
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} title="按计划日期过滤" />
        {date && <button className="btn" onClick={() => setDate("")}>清除日期</button>}
        <span className="muted">共 {runs.length} 条</span>
      </div>
      {error && <p className="error-text">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>run_id</th><th>任务</th><th>状态</th><th>触发</th>
            <th>计划时间</th><th>开始</th><th>结束</th><th>耗时</th><th>退出码</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.run_id}>
              <td><Link href={`/runs/${r.run_id}`} className="mono">{r.run_id}</Link></td>
              <td className="mono">{r.task_id}</td>
              <td>
                <span
                  className="badge"
                  style={{ background: statusColor(r.status) }}
                  title={r.missed_schedule_at ? `漏执行：${r.missed_schedule_at}` : undefined}
                >
                  {statusLabel(r.status)}
                </span>
                {r.missed_schedule_at && <span style={{ color: "#7c3aed", fontSize: 11, marginLeft: 4 }}>漏</span>}
              </td>
              <td>{r.trigger === "manual" ? "手动" : "定时"}</td>
              <td className="muted" title={r.scheduled_at || undefined}>{fmtTime(r.scheduled_at)}</td>
              <td className="muted" title={r.started_at || undefined}>{fmtTime(r.started_at)}</td>
              <td className="muted" title={r.finished_at || undefined}>{fmtTime(r.finished_at)}</td>
              <td className="muted">{r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "-"}</td>
              <td className="mono">{r.exit_code ?? "-"}</td>
            </tr>
          ))}
          {runs.length === 0 && (
            <tr><td colSpan={9} className="muted">暂无运行记录</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <RunsInner />
    </Suspense>
  );
}
