"use client";

// 单日 Token 用量摘要行：数字缩写（8.5k / 1.2M）+ ≈cost 两位小数（美元估算，不换算汇率）。
// 取数失败（后端未升级 / 404）时整行不渲染，不阻塞时间线主体。
import { machineMeta, usageByMachine, type UsageBucket } from "@/lib/api";
import { useUsage } from "@/lib/hooks";

/** 1234 → 1.2k，1200000 → 1.2M */
export function fmtTokens(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

export function fmtCost(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "≈$0.00";
  return `≈$${n.toFixed(2)}`;
}

function MachineUsage({ m, bucket }: { m: string; bucket: UsageBucket }) {
  const meta = machineMeta(m);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
      <span className={`inline-block w-2 h-2 rounded-full ${meta.dot}`} />
      {meta.label}
      <span className="text-gray-700 tabular-nums">
        {fmtTokens(bucket.input_tokens)}↓ {fmtTokens(bucket.output_tokens)}↑ {fmtTokens(bucket.cache_read_tokens)}c
      </span>
      <span className="tabular-nums">{fmtCost(bucket.cost)}</span>
    </span>
  );
}

export function UsageRow({ date }: { date: string }) {
  const { data } = useUsage(date);
  if (!data) return null;
  const machines = Object.entries(usageByMachine(data));
  return (
    <div className="flex items-center justify-center gap-5 flex-wrap mb-4 text-gray-400">
      {machines.map(([m, bucket]) => (
        <MachineUsage key={m} m={m} bucket={bucket} />
      ))}
      <span className="inline-flex items-center gap-1.5 text-xs text-gray-500 border-l border-gray-200 pl-5">
        合计 <span className="text-gray-700 tabular-nums">{data.totals.calls} 次</span>
        <span className="tabular-nums">{fmtCost(data.totals.cost)}</span>
      </span>
    </div>
  );
}
