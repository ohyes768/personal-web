"use client";

// 项目维度：按仓库聚合卡片
import { useProjects } from "@/lib/hooks";
import { fmtRelative } from "@/lib/time";
import { Empty, ErrorState, Loading } from "@/components/States";

export default function ProjectsPage() {
  const { data, loading, error, reload } = useProjects();

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.length === 0) return <Empty hint="还没有项目活动" />;

  const sorted = [...data].sort((a, b) => (b.last_active_at ?? "").localeCompare(a.last_active_at ?? ""));

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
      {sorted.map((p) => (
        <section key={p.project} className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col">
          <div className="flex items-baseline gap-2">
            <h2 className="text-sm font-semibold">{p.project}</h2>
            <span className="ml-auto text-xs text-gray-400">{fmtRelative(p.last_active_at)}</span>
          </div>
          <div className="flex gap-4 mt-2 text-xs text-gray-500">
            <span>
              会话 <strong className="text-gray-700">{p.session_count}</strong>
            </span>
            <span>
              提交 <strong className="text-gray-700">{p.commit_count}</strong>
            </span>
          </div>
          {p.recent.length > 0 && (
            <ul className="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
              {p.recent.map((s, i) => (
                <li key={i} className="text-xs text-gray-600 flex gap-2">
                  <span className="text-gray-300">·</span>
                  <span className="min-w-0">{s}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
