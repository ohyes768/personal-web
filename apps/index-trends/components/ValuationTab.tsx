"use client";

/** 估值页：价格走势与 PB/PE 分位合并成一张图（双 y 轴、同一时间轴）。
 *
 * 纯估值指数（创业板50）与通道指数共用这个视图；通道指数另有通道图，
 * 这里不画通道位置——价格是行情，分位是估值，通道是另一层拟合。
 * PB 为主、PE 用来交叉验证，选择器只换分位那条线，价格线始终在。
 */
import { useEffect, useState } from "react";
import ValuationChart from "./ValuationChart";
import { api } from "../lib/api";
import {
  VALUATION_METRIC_LABELS,
  type Valuation,
  type ValuationMetric,
  type ValuationMetricSnapshot,
} from "../lib/types";
import type { PriceSeries, ValuationHistory } from "../lib/types";

interface Props {
  code: string;
  reloadKey: number;
  /** 该指数也有周线通道：文案区分两套口径并列。 */
  hasChannel?: boolean;
}

/** 旧后端只给顶层 PE 平铺字段时按 PE 降级（与退役的 ValuationBlock 同规则）。 */
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

function emptyHistory(code: string, metric: string): ValuationHistory {
  return { index_code: code, metric, window: "y10", dates: [], values: [], percentiles: [] };
}

function rangeOf(history: ValuationHistory | null): string | null {
  return history && history.dates.length > 0
    ? `${history.dates[0]} – ${history.dates[history.dates.length - 1]}`
    : null;
}

export default function ValuationTab({ code, reloadKey, hasChannel = false }: Props) {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [prices, setPrices] = useState<PriceSeries | null>(null);
  const [histories, setHistories] = useState<Partial<Record<ValuationMetric, ValuationHistory>>>({});
  const [metric, setMetric] = useState<ValuationMetric>("pb_mcw");
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.valuation(code),
      api.prices(code, 520), // 约 10 年周收盘，与分位历史的 10 年窗口对齐
      api.valuationHistory(code, "pb_mcw"),
      api.valuationHistory(code, "pe_ttm_mcw"),
    ])
      .then(([v, p, pb, pe]) => {
        if (cancelled) return;
        setValuation(v);
        setPrices(p);
        setHistories({ pb_mcw: pb, pe_ttm_mcw: pe });
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [code, hasChannel, reloadKey, retryTick]);

  const snapshot = metricSnapshot(valuation, metric);
  const selectedHistory = histories[metric] ?? null;
  const priceRange =
    prices && prices.bars.length > 0
      ? `${prices.bars[0].date} – ${prices.bars[prices.bars.length - 1].date}`
      : null;
  const metricLabel = metric === "pb_mcw" ? "PB" : "PE-TTM";

  return (
    <section>
      {!valuation && !error && <div className="message">加载中…</div>}
      {error && (
        <div className="message error">
          加载失败：{error}
          <br />
          <button className="retry-btn" onClick={() => setRetryTick((t) => t + 1)}>
            重试
          </button>
        </div>
      )}

      {prices && (
        <div className="chart-card valuation-combined">
          <div className="close-line">
            <span className="valuation-metric">
              <small style={{ color: "#8c6847" }}>最近收盘</small>
              <b>{prices.close?.toFixed(2) ?? "—"}</b>
              <small>收盘日 {prices.price_as_of ?? "—"}</small>
            </span>
            <span className="valuation-metric">
              <div className="picker" role="tablist" aria-label="估值指标">
                {(Object.keys(VALUATION_METRIC_LABELS) as ValuationMetric[]).map((item) => (
                  <button key={item} aria-current={metric === item} onClick={() => setMetric(item)}>
                    {VALUATION_METRIC_LABELS[item]}
                  </button>
                ))}
              </div>
              <b>
                {typeof snapshot?.percentile_pct === "number"
                  ? `${snapshot.percentile_pct.toFixed(1)}%`
                  : "—"}
              </b>
              <small>
                {metricLabel}{" "}
                {typeof snapshot?.value === "number" ? snapshot.value.toFixed(2) : "—"} ·{" "}
                {snapshot?.as_of ?? "无数据"} · 理杏仁
              </small>
            </span>
          </div>

          {selectedHistory && selectedHistory.dates.length > 0 ? (
            <ValuationChart
              prices={prices}
              percentile={selectedHistory}
              reloadKey={reloadKey + retryTick}
            />
          ) : (
            <div className="valuation-muted">暂无分位历史</div>
          )}

          <div className="range-note">
            <span>周收盘 {priceRange ?? "—"}</span>
            <span>分位 {rangeOf(selectedHistory) ?? "—"}</span>
            <span>{hasChannel ? "价格与分位同图，两套口径" : "不拟合回归通道"}</span>
          </div>
        </div>
      )}

      <div className="notes">
        <div className="note-item">
          {hasChannel
            ? "一张图两个口径：左轴周收盘价是行情，右轴分位是相对自身历史估值的贵贱。价格走势与通道位置是两回事：通道位置还要叠加拟合出的轨道，分位只看估值。"
            : "一张图两个口径：左轴周收盘价是行情，右轴分位是相对自身历史估值的贵贱。该指数不拟合回归通道，所以没有通道位置、轨道与趋势延伸。"}
        </div>
        <div className="note-item">
          PB / PE-TTM 近10年分位来自理杏仁（总市值加权），是
          <span className="emphasis">独立的估值口径</span>。口径以 PB 为主：
          创业板盈利波动大，PE 的分母不稳；PE 用来交叉验证。
        </div>
      </div>
    </section>
  );
}
