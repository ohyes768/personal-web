"use client";

/** 估值块：PB 为主、PE-TTM 为辅，两条指标各自判状态 + 分位走势图。
 *
 * 与通道位置严格区分：通道位置是相对趋势通道，分位是相对自身历史估值。
 * 旧后端只给顶层 PE 平铺字段时按 PE 降级。
 */
import { useState } from "react";
import PercentileChart from "./PercentileChart";
import {
  VALUATION_METRIC_LABELS,
  type Valuation,
  type ValuationMetric,
  type ValuationMetricSnapshot,
} from "../lib/types";

/** 单条指标的读数：PB 为主、PE-TTM 为辅，各自独立判状态。
 *
 * 与通道位置严格区分：通道位置是相对趋势通道，分位是相对自身历史估值。
 * 旧后端只给顶层 PE 平铺字段时按 PE 降级，不影响主图。
 */
function metricSnapshot(
  valuation: Valuation | null,
  metric: ValuationMetric,
): ValuationMetricSnapshot | null {
  if (!valuation) return null;
  const explicit = valuation.metrics?.[metric];
  if (explicit) return explicit;
  if (metric !== "pe_ttm_mcw") return null;
  return {
    state: valuation.state,
    reason: valuation.reason,
    metric,
    source: valuation.source,
    window: valuation.window,
    target_date: valuation.target_date,
    as_of: valuation.as_of,
    value: valuation.value ?? valuation.pe_ttm,
    percentile_pct: valuation.percentile_pct,
    captured_at: valuation.captured_at,
  };
}

export default function ValuationBlock({
  code,
  valuation,
  reloadKey,
}: {
  code: string;
  valuation: Valuation | null;
  reloadKey: number;
}) {
  const [metric, setMetric] = useState<ValuationMetric>("pb_mcw");
  const snapshot = metricSnapshot(valuation, metric);
  const pct = snapshot?.percentile_pct ?? null;
  const value = snapshot?.value ?? null;
  const metricLabel = metric === "pb_mcw" ? "PB" : "PE-TTM";

  let stateNote: string | null = null;
  if (!valuation) stateNote = "暂不可用";
  else if (snapshot?.state === "disabled") stateNote = "未启用（未配置理杏仁访问令牌）";
  else if (snapshot?.state === "empty") stateNote = "暂无估值数据";
  else if (snapshot?.state === "error")
    stateNote = `暂不可用${snapshot.reason ? `（${snapshot.reason}）` : ""}`;
  else if (snapshot?.state === "stale")
    stateNote = `未更新至 ${snapshot.target_date ?? "目标日"}`;

  return (
    <div className="valuation-block">
      <div className="valuation-line">
        <div className="picker" role="tablist" aria-label="估值指标">
          {(Object.keys(VALUATION_METRIC_LABELS) as ValuationMetric[]).map((item) => (
            <button key={item} aria-current={metric === item} onClick={() => setMetric(item)}>
              {VALUATION_METRIC_LABELS[item]}
            </button>
          ))}
        </div>
        <b>{typeof pct === "number" ? `${pct.toFixed(1)}%` : "—"}</b>
        <small>
          {metricLabel} {typeof value === "number" ? value.toFixed(2) : "—"} ·{" "}
          {snapshot?.as_of ?? "无数据"} · 理杏仁
        </small>
        {stateNote && <span className="valuation-muted">{stateNote}</span>}
      </div>
      <PercentileChart code={code} metric={metric} reloadKey={reloadKey} />
    </div>
  );
}

