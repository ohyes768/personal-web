"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiGet, Run, statusColor, statusLabel } from "@/lib/api";

const STATUS_OPTIONS = ["", "waiting", "running", "success", "failed", "timeout", "interrupted", "skipped"];

function RunsInner() {
  const sp = useSearchParams();
  const [taskId, setTaskId] = useState(sp.get("task_id") || "");
  const [status, setStatus] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (taskId) params.set("task_id", taskId);
      if (status) params.set("status", status);
      const data = await apiGet<{ runs: Run[] }>(`/runs?${params}`);
      setRuns(data.runs);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, [taskId, status]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div>
      <div className="filters">
        <input
          placeholder="task_id"
          value={taskId} onChange={(e) => setTaskId(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s ? statusLabel(s) : "全部状态"}</option>
          ))}
        </select>
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
                <span className="badge" style={{ background: statusColor(r.status) }}>
                  {statusLabel(r.status)}
                </span>
                {r.missed_schedule_at && (
                  <div className="muted">漏执行：{r.missed_schedule_at}</div>
                )}
              </td>
              <td>{r.trigger === "manual" ? "手动" : "定时"}</td>
              <td className="muted">{r.scheduled_at || "-"}</td>
              <td className="muted">{r.started_at || "-"}</td>
              <td className="muted">{r.finished_at || "-"}</td>
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
