"use client";

// GitHub 贡献格子热力图：列=周（最新在右），行=周一~周日，起点对齐当周周一。
// 格子指标 = input+output tokens（不含 cache_read——cache 占比 ~98% 会把所有格子挤到最深档）。
//
// 分档阈值按 NAS 真实数据校准（usage?days=60，in+out 逐日求和，log 刻度）：
//   高产日 63M/45M/36M/12M/10M（11-13/14/15/12/25），日常 1.5M~4.8M，
//   低产日 8k~400k，非活跃日 0。
//   v0 空 / v1 >0~150k / v2 150k~1M / v3 1M~4M / v4 >4M
// 偏浅/偏深时直接调 THRESHOLDS。
import { useMemo } from "react";
import { usageByMachine } from "@/lib/api";
import { useUsageDays } from "@/lib/hooks";
import { fmtCost, fmtTokens } from "@/components/UsageRow";

const DAYS = 182; // 26 周
const THRESHOLDS = [150_000, 1_000_000, 4_000_000]; // v1 ≤150k，v2 ≤1M，v3 ≤4M，>4M 为 v4

const LEVEL_CLASS = [
  "bg-gray-100", // v0 空
  "bg-green-200",
  "bg-green-400",
  "bg-green-600",
  "bg-green-800",
];

function levelOf(inOut: number): number {
  if (inOut <= 0) return 0;
  let lv = 1;
  for (const t of THRESHOLDS) {
    if (inOut > t) lv++;
    else break;
  }
  return lv;
}

const fmtDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function ContributionGrid({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (date: string) => void;
}) {
  const { data } = useUsageDays(DAYS);

  // 同日可能两行（nas/windows），按 date 求和合并 in+out；附 calls/cost 供 tooltip
  const daily = useMemo(() => {
    const map = new Map<string, { inOut: number; calls: number; cost: number }>();
    for (const r of data?.by_day_machine ?? []) {
      const cur = map.get(r.date) ?? { inOut: 0, calls: 0, cost: 0 };
      cur.inOut += r.input_tokens + r.output_tokens;
      cur.calls += r.calls;
      cur.cost += r.cost;
      map.set(r.date, cur);
    }
    return map;
  }, [data]);

  // 周列：从 start（N 天前对齐周一）到今天
  const cells = useMemo(() => {
    const today = new Date();
    const todayStr = fmtDay(today);
    const start = new Date(today);
    start.setDate(start.getDate() - (DAYS - 1));
    const dow = (start.getDay() + 6) % 7; // 周一=0
    start.setDate(start.getDate() - dow);

    const weeks: { date: string; inOut: number; calls: number; cost: number; future: boolean }[][] = [];
    const cur = new Date(start);
    while (cur <= today) {
      const week: typeof weeks[number] = [];
      for (let i = 0; i < 7; i++) {
        const ds = fmtDay(cur);
        const stat = daily.get(ds);
        week.push({
          date: ds,
          inOut: stat?.inOut ?? 0,
          calls: stat?.calls ?? 0,
          cost: stat?.cost ?? 0,
          future: ds > todayStr,
        });
        cur.setDate(cur.getDate() + 1);
      }
      weeks.push(week);
    }
    return weeks;
  }, [daily]);

  const totals = data?.totals;
  const totalInOut = totals ? totals.input_tokens + totals.output_tokens : 0;

  if (!data || !totals) return null; // 取数失败/旧后端：热力图整体隐藏，不阻塞下方内容

  return (
    <div className="mb-6">
      <div className="text-xs text-gray-400 mb-2 tabular-nums">
        近 26 周 · {totals.calls} 次 · {fmtTokens(totalInOut)} tokens
      </div>
      <div className="overflow-x-auto pb-1">
        <div className="inline-grid grid-flow-col gap-[3px]">
          {cells.map((week) =>
            week.map((c) => {
              if (c.future) return null; // 今天之后不渲染
              const lv = levelOf(c.inOut);
              const sel = c.date === selected;
              return (
                <button
                  key={c.date}
                  onClick={() => onSelect(c.date)}
                  title={`${c.date} · ${c.calls} 次 · in+out ${fmtTokens(c.inOut)} · ${fmtCost(c.cost)}`}
                  className={`w-[11px] h-[11px] rounded-[2px] ${LEVEL_CLASS[lv]} cursor-pointer ${
                    sel ? "ring-2 ring-orange-400 ring-offset-0" : "hover:ring-1 hover:ring-gray-400"
                  }`}
                />
              );
            }),
          )}
        </div>
      </div>
    </div>
  );
}
