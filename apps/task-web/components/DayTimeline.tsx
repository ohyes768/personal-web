"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { ScheduleSlot, ScheduleTaskView } from "@/lib/api";
import { statusColor, statusLabel } from "@/lib/api";

/** "2026-11-07T09:30:00" → 0~1 的当日时间占比。 */
function timeFrac(at: string): number {
  const h = Number(at.slice(11, 13)) || 0;
  const m = Number(at.slice(14, 16)) || 0;
  const s = Number(at.slice(17, 19)) || 0;
  return (h * 3600 + m * 60 + s) / 86400;
}

function hhmm(at: string): string {
  return at.slice(11, 16);
}

/**
 * 单日排期轴：每任务一行 0–24h 横轴。
 * 实心点=run（颜色取 statusColor）、空心=未来计划、虚线空心=pending（待漏执行判定）、
 * 方块=手动触发；同一 HH:MM ≥2 个任务 → 琥珀竖带 + 顶部提示条。
 */
export default function DayTimeline({ tasks, date, todayStr }: {
  tasks: ScheduleTaskView[];
  date: string;
  todayStr: string;
}) {
  const isToday = date === todayStr;
  const now = new Date();
  const nowFrac = (now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()) / 86400;

  const clusters = useMemo(() => {
    const byMinute = new Map<string, Set<string>>();
    for (const t of tasks) {
      for (const s of t.slots) {
        const key = s.at.slice(0, 16);
        const set = byMinute.get(key) ?? new Set<string>();
        set.add(t.id);
        byMinute.set(key, set);
      }
    }
    return [...byMinute.entries()]
      .filter(([, ids]) => ids.size >= 2)
      .map(([key, ids]) => ({
        minute: key.slice(11, 16),
        frac: timeFrac(`${key}:00`),
        names: tasks.filter((t) => ids.has(t.id)).map((t) => t.name),
      }))
      .sort((a, b) => a.frac - b.frac);
  }, [tasks]);

  function renderSlot(t: ScheduleTaskView, s: ScheduleSlot, i: number) {
    const left = { left: `${timeFrac(s.at) * 100}%` };
    const key = `s${i}`;
    if (s.kind === "run" && s.run) {
      const r = s.run;
      const dur = r.duration_ms != null ? ` · ${(r.duration_ms / 1000).toFixed(1)}s` : "";
      return (
        <Link
          key={key} href={`/runs/${r.run_id}`} className="slot-dot"
          style={{ ...left, background: statusColor(r.status) }}
          title={`${t.name} · ${hhmm(s.at)} · ${statusLabel(r.status)}${dur}`}
        />
      );
    }
    if (s.kind === "pending") {
      return (
        <span key={key} className="slot-dot pending-dot" style={left}
          title={`${t.name} · ${hhmm(s.at)} · 已到计划时刻，暂无记录（待漏执行判定）`} />
      );
    }
    return (
      <span key={key} className="slot-dot hollow" style={left}
        title={`${t.name} · ${hhmm(s.at)} · 计划`} />
    );
  }

  return (
    <div>
      <div className="ruler">
        <span style={{ left: 0 }}>0</span>
        <span style={{ left: "25%" }}>6</span>
        <span style={{ left: "50%" }}>12</span>
        <span style={{ left: "75%" }}>18</span>
        <span style={{ left: "100%" }}>24</span>
      </div>
      {clusters.length > 0 && (
        <div className="cluster-note">
          ⚠ 时间扎堆：{clusters.map((c) => `${c.minute}（${c.names.length} 个）`).join("、")}
          <div className="muted" style={{ marginTop: 2 }}>
            {[...new Set(clusters.flatMap((c) => c.names))].join(" / ")}
          </div>
        </div>
      )}
      {tasks.length === 0 && <p className="muted">该筛选条件下无任务</p>}
      {tasks.map((t) => (
        <div className="slot-row" key={t.id}>
          <div className="slot-lbl" title={t.cron ? `${t.name}（${t.cron}）` : t.name}>
            <strong style={{ fontSize: 12 }}>{t.name}</strong>
            {!t.enabled && (
              <span className="badge" style={{ background: "#6b7280", marginLeft: 4, fontSize: 10 }}>停用</span>
            )}
            {!t.cron_valid && (
              <span className="badge" style={{ background: "#dc2626", marginLeft: 4, fontSize: 10 }}>cron 非法</span>
            )}
          </div>
          <div className="slot-track">
            {clusters.map((c) => (
              <span key={c.minute} className="slot-band" style={{ left: `${c.frac * 100}%` }} />
            ))}
            {isToday && <span className="slot-now" style={{ left: `${nowFrac * 100}%` }} />}
            {t.slots.map((s, i) => renderSlot(t, s, i))}
            {t.manual.map((m, i) => (
              <Link
                key={`m${i}`} href={`/runs/${m.run.run_id}`} className="slot-dot square"
                style={{ left: `${timeFrac(m.at) * 100}%` }}
                title={`${t.name} · ${hhmm(m.at)} · 手动触发 · ${statusLabel(m.run.status)}`}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
