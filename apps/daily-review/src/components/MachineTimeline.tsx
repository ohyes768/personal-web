"use client";

// 双机活动时间线：windows / nas 各占一列，机器身份由列位置 + 色点表达，不再加文字说明。
import { machineMeta, type ActivityItem } from "@/lib/api";
import { fmtTime } from "@/lib/time";

export function MachineTimeline({ items }: { items: ActivityItem[] }) {
  const machines = [...new Set(items.map((it) => it.machine))];
  if (machines.length === 0) return null;

  const byMachine = new Map<string, ActivityItem[]>();
  for (const it of items) {
    const list = byMachine.get(it.machine) ?? [];
    list.push(it);
    byMachine.set(it.machine, list);
  }
  for (const list of byMachine.values()) {
    list.sort((a, b) => a.started_at.localeCompare(b.started_at));
  }

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${machines.length}, minmax(0, 1fr))` }}>
      {machines.map((m) => {
        const meta = machineMeta(m);
        return (
          <section key={m} className="bg-white border border-gray-200 rounded-lg p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold mb-3">
              <span className={`inline-block w-2.5 h-2.5 rounded-full ${meta.dot}`} />
              {meta.label}
            </h2>
            <ol className="space-y-0">
              {byMachine.get(m)!.map((it, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-10 flex-none text-xs text-gray-400 pt-0.5 tabular-nums text-right">
                    {fmtTime(it.started_at)}
                  </span>
                  <span className="flex-none flex flex-col items-center pt-1.5">
                    <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                    {i < byMachine.get(m)!.length - 1 && (
                      <span className="w-px flex-1 bg-gray-200 mt-1" />
                    )}
                  </span>
                  <div className="pb-4 min-w-0">
                    <p className="text-sm font-medium truncate">
                      <span className="text-gray-400 font-normal mr-1.5">{it.project}</span>
                      {it.title}
                    </p>
                    {it.summary_text && (
                      <p className="text-xs text-gray-500 mt-0.5 whitespace-pre-wrap">{it.summary_text}</p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        );
      })}
    </div>
  );
}
