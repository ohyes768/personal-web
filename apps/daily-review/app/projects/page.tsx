"use client";

// 项目维度：窗口切换（近7天/近30天/全部）+ 按窗口内活动量降序的卡片
// 卡片：会话/提交/活跃天数 + 近 14 天迷你条形（让布局解释活跃节奏）+ 最近摘要 5 条
import { useState } from "react";
import { useProjects } from "@/lib/hooks";
import { fmtRelative } from "@/lib/time";
import { Empty, ErrorState, Loading } from "@/components/States";

const WINDOWS = [
  { days: 7, label: "近 7 天" },
  { days: 30, label: "近 30 天" },
  { days: 0, label: "全部" },
];

export default function ProjectsPage() {
  const [days, setDays] = useState(7);
  const { data, loading, error, reload } = useProjects(days);

  return (
    <div>
      <div className="flex gap-1 mb-4">
        {WINDOWS.map((w) => (
          <button
            key={w.days}
            onClick={() => setDays(w.days)}
            className={`px-4 py-1.5 text-sm rounded-md border cursor-pointer ${
              days === w.days
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white border-gray-300 hover:bg-gray-50"
            }`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <Empty hint="窗口内没有项目活动" />
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))" }}>
          {data.map((p) => (
            <section key={p.project} className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col">
              <div className="flex items-baseline gap-2">
                <h2 className="text-sm font-semibold">{p.project}</h2>
                <span className="ml-auto text-xs text-gray-400">{fmtRelative(p.last_activity)}</span>
              </div>
              <div className="flex gap-4 mt-2 text-xs text-gray-500">
                <span>
                  会话 <strong className="text-gray-700">{p.session_count}</strong>
                </span>
                <span>
                  提交 <strong className="text-gray-700">{p.commit_count}</strong>
                </span>
                <span>
                  活跃 <strong className="text-gray-700">{p.active_days}</strong> 天
                </span>
              </div>
              {/* 近 14 天活跃节奏：每日活动量条形 */}
              <div className="flex items-end gap-[3px] h-8 mt-3">
                {p.daily_counts.map((d) => (
                  <div
                    key={d.day}
                    title={`${d.day}：${d.count}`}
                    className="flex-1 rounded-sm bg-blue-200"
                    style={{ height: `${d.count === 0 ? 2 : Math.min(100, (d.count / maxCount(p)) * 100)}%` }}
                  />
                ))}
              </div>
              {p.recent_summaries.length > 0 && (
                <ul className="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
                  {p.recent_summaries.map((s, i) => (
                    <li key={i} className="text-xs text-gray-600 flex gap-2">
                      <span
                        className={`flex-none mt-0.5 px-1.5 rounded text-[10px] leading-4 ${
                          s.machine === "windows" ? "bg-sky-100 text-sky-700" : "bg-emerald-100 text-emerald-700"
                        }`}
                        title={s.machine === "windows" ? "来自 Windows" : "来自 NAS"}
                      >
                        {s.machine === "windows" ? "win" : "nas"}
                      </span>
                      <span className="min-w-0">{s.title}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function maxCount(p: { daily_counts: { count: number }[] }): number {
  return Math.max(1, ...p.daily_counts.map((d) => d.count));
}
