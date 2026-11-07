"use client";

import type { ScheduleSummaryDay } from "@/lib/api";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 6 行 × 7 列（周一起始）的月度格子，含前后月补位。 */
function monthCells(year: number, month: number): { date: string; inMonth: boolean }[] {
  const offset = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const start = new Date(year, month - 1, 1 - offset);
  const cells: { date: string; inMonth: boolean }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    cells.push({ date: fmtDate(d), inMonth: d.getMonth() === month - 1 });
  }
  return cells;
}

interface Props {
  viewYear: number;
  viewMonth: number;
  selectedDate: string;
  days: Record<string, ScheduleSummaryDay>;
  todayStr: string;
  onSelectDate: (date: string) => void;
  onShiftMonth: (delta: number) => void;
}

/**
 * 月历总览：每格 = 当日状态计数（绿=成功、红=失败/超时/中断、紫=漏执行）。
 * 底色优先级：异常红 > 漏执行紫 > 全成功绿；未来灰。底色语义与 prd.md 一致。
 */
export default function MonthCalendar({
  viewYear, viewMonth, selectedDate, days, todayStr, onSelectDate, onShiftMonth,
}: Props) {
  const cells = monthCells(viewYear, viewMonth);
  return (
    <div className="panel cal-panel">
      <div className="cal-head">
        <button className="btn" onClick={() => onShiftMonth(-1)} aria-label="上个月">‹</button>
        <span className="cal-title">{viewYear}年{viewMonth}月</span>
        <button className="btn" onClick={() => onShiftMonth(1)} aria-label="下个月">›</button>
        <button className="btn" style={{ marginLeft: "auto" }} onClick={() => onSelectDate(todayStr)}>
          回到今天
        </button>
      </div>
      <div className="cal-grid">
        {WEEKDAYS.map((w) => <div key={w} className="cal-wd">{w}</div>)}
        {cells.map(({ date, inMonth }) => {
          const s = days[date];
          const abnormal = s ? s.failed + s.timeout + s.interrupted : 0;
          const missed = s?.missed ?? 0;
          const done = s ? s.success + s.skipped : 0;
          const isFuture = date > todayStr;
          let cls = "cal-cell";
          if (!inMonth) cls += " out";
          else if (isFuture) cls += " future";
          else if (abnormal > 0) cls += " bad";
          else if (missed > 0) cls += " miss";
          else if (done > 0) cls += " ok";
          if (date === selectedDate) cls += " sel";
          const title = s
            ? `${date}：成功 ${s.success} · 失败 ${s.failed + s.timeout} · 漏 ${missed}`
            : isFuture ? `${date}（计划）` : `${date}（无记录）`;
          return (
            <div key={date} className={cls} title={title} onClick={() => onSelectDate(date)}>
              <span className="cal-n" style={date === todayStr ? { color: "#2563eb" } : undefined}>
                {Number(date.slice(8))}
              </span>
              <div className="chips">
                {done > 0 && <i className="chip g">{done}</i>}
                {abnormal > 0 && <i className="chip r">{abnormal}</i>}
                {missed > 0 && <i className="chip p">{missed}</i>}
                {isFuture && inMonth && <span className="chip empty">计划</span>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="muted" style={{ marginTop: 8, marginBottom: 0 }}>
        绿=全部成功 红=有失败 紫=有漏执行 灰=未来计划
      </p>
    </div>
  );
}
