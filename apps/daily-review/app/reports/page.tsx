"use client";

// 报告列表：日报（周报已取消）
import Link from "next/link";
import { useReports } from "@/lib/hooks";
import { fmtDateTime } from "@/lib/time";
import { Empty, ErrorState, Loading } from "@/components/States";


export default function ReportsPage() {
  const { data, loading, error, reload } = useReports("daily");

  return (
    <div>
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
