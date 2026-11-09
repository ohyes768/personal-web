"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiGet, Run, statusColor, statusLabel } from "@/lib/api";

interface RunDetail extends Run {
  log_path: string | null;
}

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [stdout, setStdout] = useState("");
  const [stderr, setStderr] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await apiGet<RunDetail>(`/runs/${runId}`);
      setRun(r);
      const logs = await apiGet<{ stdout: string; stderr: string }>(
        `/runs/${runId}/logs`
      );
      setStdout(logs.stdout);
      setStderr(logs.stderr);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, [runId]);

  // 初始加载一次；只有运行中/等待中的 run 才继续 3s 轮询，终态停止
  useEffect(() => {
    load();
  }, [load]);

  const isRunning = run?.status === "running" || run?.status === "waiting";

  useEffect(() => {
    if (!isRunning) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [isRunning, load]);

  if (error) return <p className="error-text">{error}</p>;
  if (!run) return <p className="muted">加载中…</p>;

  return (
    <div>
      <table style={{ marginBottom: 16 }}>
        <tbody>
          <tr><th>run_id</th><td className="mono">{run.run_id}</td></tr>
          <tr><th>任务</th><td className="mono">{run.task_id}</td></tr>
          <tr>
            <th>状态</th>
            <td>
              <span className="badge" style={{ background: statusColor(run.status) }}>
                {statusLabel(run.status)}
              </span>
              {run.missed_schedule_at && (
                <span className="muted"> （漏执行：{run.missed_schedule_at}）</span>
              )}
            </td>
          </tr>
          <tr><th>触发</th><td>{run.trigger === "manual" ? "手动" : "定时"}</td></tr>
          <tr><th>计划 / 开始 / 结束</th>
            <td className="muted">{run.scheduled_at || "-"} / {run.started_at || "-"} / {run.finished_at || "-"}</td></tr>
          <tr><th>耗时 / 退出码</th>
            <td>
              {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-"} /{" "}
              <span className="mono">{run.exit_code ?? "-"}</span>
              <span className="muted">（退出码 0 只代表进程正常退出，不代表业务投递成功）</span>
            </td></tr>
        </tbody>
      </table>

      <h3>stdout {isRunning && <span className="muted">（运行中，3s 自动刷新）</span>}</h3>
      <pre className="log-box">{stdout || "（无输出）"}</pre>

      <h3>stderr</h3>
      <pre className="log-box">{stderr || "（无输出）"}</pre>
    </div>
  );
}
