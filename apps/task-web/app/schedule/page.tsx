"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ScheduleDayView, ScheduleSummaryDay, ScheduleTaskView } from "@/lib/api";
import { apiGet } from "@/lib/api";
import MonthCalendar from "@/components/MonthCalendar";
import DayTimeline from "@/components/DayTimeline";

const GROUP_TABS: { key: "script" | "ai"; label: string }[] = [
  { key: "script", label: "脚本任务" },
  { key: "ai", label: "AI 任务" },
];

const WEEKDAY_NAMES = ["日", "一", "二", "三", "四", "五", "六"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function validDate(s: string | null): string | null {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  return Number.isNaN(new Date(`${s}T00:00:00`).getTime()) ? null : s;
}

/** 异常槽：实际失败（failed/timeout/interrupted）或 pending（已过计划时刻暂无记录）。 */
function hasIssue(t: ScheduleTaskView): boolean {
  return t.slots.some(
    (s) => s.kind === "pending"
      || (s.run != null && ["failed", "timeout", "interrupted"].includes(s.run.status)),
  );
}

function ScheduleInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const todayStr = fmtDate(new Date());
  const initialDate = validDate(sp.get("date")) ?? todayStr;

  const [date, setDate] = useState(initialDate);
  const [viewYear, setViewYear] = useState(() => Number(initialDate.slice(0, 4)));
  const [viewMonth, setViewMonth] = useState(() => Number(initialDate.slice(5, 7)));
  const [summary, setSummary] = useState<Record<string, ScheduleSummaryDay>>({});
  const [day, setDay] = useState<ScheduleDayView | null>(null);
  const [groupTab, setGroupTab] = useState<"script" | "ai">("script");
  const [onlyIssue, setOnlyIssue] = useState(false);
  const [error, setError] = useState("");

  const loadSummary = useCallback(async (y: number, m: number) => {
    try {
      const from = `${y}-${pad(m)}-01`;
      const to = `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`;
      const data = await apiGet<{ days: ScheduleSummaryDay[] }>(
        `/schedule/summary?from=${from}&to=${to}`);
      const map: Record<string, ScheduleSummaryDay> = {};
      for (const d of data.days) map[d.date] = d;
      setSummary(map);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadDay = useCallback(async (d: string) => {
    try {
      const data = await apiGet<ScheduleDayView>(`/schedule/day?date=${d}`);
      setDay(data);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    loadSummary(viewYear, viewMonth);
    const t = setInterval(() => loadSummary(viewYear, viewMonth), 30000);
    return () => clearInterval(t);
  }, [loadSummary, viewYear, viewMonth]);

  useEffect(() => {
    loadDay(date);
    const t = setInterval(() => loadDay(date), 5000);
    return () => clearInterval(t);
  }, [loadDay, date]);

  function selectDate(d: string) {
    setDate(d);
    setViewYear(Number(d.slice(0, 4)));
    setViewMonth(Number(d.slice(5, 7)));
    router.replace(`/schedule?date=${d}`, { scroll: false });
  }

  function shiftMonth(delta: number) {
    const nm = new Date(viewYear, viewMonth - 1 + delta, 1);
    setViewYear(nm.getFullYear());
    setViewMonth(nm.getMonth() + 1);
  }

  const visibleTasks = useMemo(
    () => (day?.tasks ?? [])
      .filter((t) => t.group === groupTab)
      .filter((t) => !onlyIssue || hasIssue(t)),
    [day, groupTab, onlyIssue],
  );

  const weekday = WEEKDAY_NAMES[new Date(`${date}T00:00:00`).getDay()];

  return (
    <div>
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
            <span
              className="muted"
              style={{ marginLeft: 6, color: groupTab === g.key ? "#dbeafe" : undefined }}
            >
              {(day?.tasks ?? []).filter((t) => t.group === g.key).length}
            </span>
          </button>
        ))}
        <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: 13 }}>
          <input type="checkbox" checked={onlyIssue} onChange={(e) => setOnlyIssue(e.target.checked)} />
          只看异常
        </label>
        <span className="muted">显示 {visibleTasks.length} 个任务</span>
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="schedule-layout">
        <MonthCalendar
          viewYear={viewYear}
          viewMonth={viewMonth}
          selectedDate={date}
          days={summary}
          todayStr={todayStr}
          onSelectDate={selectDate}
          onShiftMonth={shiftMonth}
        />
        <div className="panel day-panel">
          <div className="cal-head">
            <span className="cal-title">{date}</span>
            <span className="muted">周{weekday}</span>
            {date === todayStr && <span className="badge" style={{ background: "#2563eb" }}>今天</span>}
          </div>
          <DayTimeline tasks={visibleTasks} date={date} todayStr={todayStr} />
          <div className="legend">
            <span><i style={{ background: "#16a34a" }} />成功</span>
            <span><i style={{ background: "#dc2626" }} />失败</span>
            <span><i style={{ background: "#7c3aed" }} />漏执行</span>
            <span><i style={{ background: "#2563eb" }} />运行中/等待</span>
            <span><i className="hollow" />未来计划</span>
            <span><i className="pending-dot" />待判定</span>
            <span><i className="sq" />手动触发</span>
            <span>红线=现在</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SchedulePage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <ScheduleInner />
    </Suspense>
  );
}
