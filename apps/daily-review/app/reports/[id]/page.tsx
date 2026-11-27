"use client";

// 报告详情：LLM 总结（markdown）+ 原始结构化记录 + 生成动作
import { useState, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { machineMeta } from "@/lib/api";
import { generateReport, useReport } from "@/lib/hooks";
import { fmtDateTime, fmtRelative, fmtTime } from "@/lib/time";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data, loading, error, reload } = useReport(id);
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);

  async function doGenerate() {
    setConfirming(null);
    setGenerating("daily");
    setGenError("");
    try {
      const { id: newId } = await generateReport("daily");
      setGenerating(null);
      router.push(`/reports/${newId}`);
    } catch (e) {
      setGenerating(null);
      setGenError(e instanceof Error ? e.message : String(e));
    }
  }

  const generateLabel: Record<string, string> = { daily: "重新生成日报" };

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return <Empty hint="报告不存在" />;

  const { report, records } = data;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Link href="/reports" className="text-sm text-gray-500 hover:text-gray-900 no-underline">
          ‹ 报告
        </Link>
        <h1 className="text-base font-semibold tabular-nums">
          {report.period_start === report.period_end
            ? report.period_start
            : `${report.period_start} ~ ${report.period_end}`}
        </h1>
        <span className="text-xs text-gray-400">{fmtRelative(report.generated_at)}生成</span>
        <div className="ml-auto flex gap-2">
          {(Object.keys(generateLabel)).map((t) => (
            <button
              key={t}
              onClick={() => setConfirming(t)}
              disabled={generating !== null}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer disabled:opacity-50"
            >
              {generating === t ? "生成中…" : generateLabel[t]}
            </button>
          ))}
        </div>
      </div>
      {genError && <p className="text-sm text-red-600 mb-3">{genError}</p>}

      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-5">
        {report.summary_md ? <Markdown md={report.summary_md} /> : <Empty hint="总结尚未生成" />}
      </div>

      <details className="mt-5 group">
        <summary className="text-sm font-semibold text-gray-500 cursor-pointer select-none">
          原始记录 <span className="font-normal text-gray-400">{records.length}</span>
          <span className="ml-2 text-xs text-gray-400 group-open:hidden">展开</span>
        </summary>
        <div className="mt-2">
      {records.length === 0 ? (
        <Empty hint="该周期没有结构化记录" />
      ) : (
        <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
          {records.map((r, i) => {
            const meta = machineMeta(r.machine);
            return (
              <li key={i} className="flex gap-3 px-4 py-2.5 text-sm">
                <span className={`flex-none w-2 h-2 rounded-full mt-1.5 ${meta.dot}`} title={meta.label} />
                <span className="flex-none text-xs text-gray-400 pt-0.5 w-11 tabular-nums text-right">
                  {fmtDateTime(r.started_at).slice(6)}
                </span>
                <div className="min-w-0">
                  <p className="truncate">
                    <span className="text-gray-400 mr-1.5">{r.project}</span>
                    {r.title}
                  </p>
                  {r.summary_text && <p className="text-xs text-gray-500 mt-0.5">{r.summary_text}</p>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
        </div>
      </details>

      {confirming && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-10">
          <div className="bg-white rounded-xl p-6 min-w-[320px]">
            <h3 className="font-semibold mb-2">{generateLabel[confirming]}</h3>
            <p className="text-sm text-gray-500 mb-4">
              将基于当天的结构化记录重新调用 LLM 生成日报，通常需要几十秒。
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirming(null)}
                className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => doGenerate()}
                className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
              >
                确认生成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
