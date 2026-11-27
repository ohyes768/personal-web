"use client";

// 报告列表：daily / weekly 两个 tab，点进详情
import { useState } from "react";
import Link from "next/link";
import { type ReportType } from "@/lib/api";
import { useReports } from "@/lib/hooks";
import { fmtDateTime } from "@/lib/time";
import { Empty, ErrorState, Loading } from "@/components/States";

const TABS: { key: ReportType; label: string }[] = [
  { key: "daily", label: "日报" },
  { key: "weekly", label: "周报" },
];

export default function ReportsPage() {
  const [type, setType] = useState<ReportType>("daily");
  const { data, loading, error, reload } = useReports(type);

  return (
    <div>
      <div className="flex gap-1 mb-4">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setType(t.key)}
            className={`px-4 py-1.5 text-sm rounded-md border cursor-pointer ${
              type === t.key
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white border-gray-300 hover:bg-gray-50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <Empty hint="还没有生成过报告" />
      ) : (
        <ul className="divide-y divide-gray-200 bg-white border border-gray-200 rounded-lg">
          {data.map((r) => (
            <li key={r.id}>
              <Link
                href={`/reports/${r.id}`}
                className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50 no-underline text-gray-900"
              >
                <span className="text-sm font-medium tabular-nums">
                  {r.period_start === r.period_end ? r.period_start : `${r.period_start} ~ ${r.period_end}`}
                </span>
                <span className="ml-auto text-xs text-gray-400">{fmtDateTime(r.generated_at)} 生成</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    r.status === "done"
                      ? "bg-green-100 text-green-700"
                      : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {r.status}
                </span>
                <span className="text-gray-300">›</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
