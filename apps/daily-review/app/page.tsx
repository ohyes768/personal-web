"use client";

// 首页 = 日报正文 + 日历翻页（‹ 日期 ›），进来直接看内容，不再先点列表。
// 默认展示最近一篇；按天翻页，超出已有范围显示空态并可就地生成。
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useDailyIndex, useReport, generateReport } from "@/lib/hooks";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/States";

const DAY_MS = 86400000;
const fmt = (d: Date) => d.toISOString().slice(0, 10);

export default function DailyHomePage() {
  const router = useRouter();
  const { dates, minDate, loading: idxLoading, error: idxError, reload: reloadIndex } = useDailyIndex();
  // 默认落在最新一篇；没有数据时落在昨天
  const initial = dates.length ? dates[dates.length - 1] : fmt(new Date(Date.now() - DAY_MS));
  const [date, setDate] = useState<string>(initial);

  const { byDate } = useDailyIndex();
  const reportId = byDate[date];
  const { data, loading, error, reload } = useReport(reportId ?? "__none__");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  async function doGenerate() {
    setGenerating(true);
    setGenError("");
    try {
      const { id } = await generateReport("daily", date);
      await reloadIndex();
      router.refresh();
      setGenerating(false);
      if (id) reload();
    } catch (e) {
      setGenerating(false);
      setGenError(e instanceof Error ? e.message : String(e));
    }
  }

  const cur = new Date(`${date}T00:00:00Z`);
  const prev = fmt(new Date(cur.getTime() - DAY_MS));
  const next = fmt(new Date(cur.getTime() + DAY_MS));
  const today = fmt(new Date());
  const atMin = date <= minDate;
  const atMax = date >= today;

  return (
    <div>
      {/* 日历翻页：‹ 日期 ›，今日之后不可前进 */}
      <div className="flex items-center justify-center gap-3 mb-5 max-w-[900px] mx-auto">
        <button
          onClick={() => setDate(prev)}
          disabled={atMin}
          className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          ‹
        </button>
        <span className="text-base font-semibold tabular-nums min-w-[110px] text-center">
          {date}
          {date === today && <span className="ml-1 text-xs font-normal text-gray-400">今天</span>}
        </span>
        <button
          onClick={() => setDate(next)}
          disabled={atMax}
          className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          ›
        </button>
      </div>

      {idxLoading ? (
        <Loading />
      ) : idxError ? (
        <ErrorState error={idxError} onRetry={reloadIndex} />
      ) : !reportId ? (
        <div>
          {genError && <p className="text-sm text-red-600 mb-3">{genError}</p>}
          <Empty hint={`${date} 还没有日报`} />
          <div className="flex justify-center mt-4">
            <button
              onClick={doGenerate}
              disabled={generating || date > today}
              className="px-4 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
            >
              {generating ? "生成中…" : `生成 ${date} 日报`}
            </button>
          </div>
        </div>
      ) : loading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || !data.report ? (
        <Empty hint="报告不存在" />
      ) : (
        <>
          <div className="bg-white border border-gray-200 rounded-lg p-5 max-w-[900px] mx-auto">
            {data.report.summary_md ? <Markdown md={data.report.summary_md} /> : <Empty hint="总结尚未生成" />}
          </div>
          {data.records.length > 0 && (
            <details className="mt-5 group max-w-[900px] mx-auto">
              <summary className="text-sm font-semibold text-gray-500 cursor-pointer select-none">
                原始记录 <span className="font-normal text-gray-400">{data.records.length}</span>
                <span className="ml-2 text-xs text-gray-400 group-open:hidden">展开</span>
              </summary>
              <div className="mt-2">
                <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
                  {data.records.map((r, i) => (
                    <li key={i} className="flex gap-3 px-4 py-2.5 text-sm">
                      <span
                        className={`flex-none px-1.5 rounded text-[10px] leading-4 mt-0.5 ${
                          r.machine === "windows" ? "bg-sky-100 text-sky-700" : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {r.machine === "windows" ? "win" : "nas"}
                      </span>
                      <span className="text-gray-400 mr-1.5">{r.project}</span>
                      {r.title}
                    </li>
                  ))}
                </ul>
              </div>
            </details>
          )}
        </>
      )}
    </div>
  );
}
