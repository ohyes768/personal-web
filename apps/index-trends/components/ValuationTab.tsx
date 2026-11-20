"use client";

/** 估值页：指数点数走势 + 悬浮查 PB/PE 分位（不画分位走势）。
 *
 * 纯估值指数（创业板50）与通道指数共用这个视图；通道指数另有通道图，
 * 这里不画通道位置——价格是行情，分位是估值，通道是另一层拟合。
 * PB / PE 两行读数并列展示，不做切换；分位只在悬浮时按日期就近查表。
 */
import { useEffect, useState } from "react";
import ValuationChart from "./ValuationChart";
import { api } from "../lib/api";
import { buildPercentileLookup } from "../lib/valuationCombinedOptions";
import {
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

/** 摘要行里一行指标的读数：标签 + 当前分位 + 指标值与数据日期。 */
function MetricReadout({ snapshot, label }: { snapshot: ValuationMetricSnapshot | null; label: string }) {
  const pct = snapshot?.percentile_pct;
  const value = snapshot?.value;
  return (
    <span className="valuation-metric">
      <small>{label}分位</small>
      <b>{typeof pct === "number" ? `${pct.toFixed(1)}%` : "—"}</b>
      <small>
        {label} {typeof value === "number" ? value.toFixed(2) : "—"} ·{" "}
        {snapshot?.as_of ?? "无数据"} · 理杏仁
      </small>
    </span>
  );
}

export default function ValuationTab({ code, reloadKey, hasChannel = false }: Props) {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [prices, setPrices] = useState<PriceSeries | null>(null);
  const [histories, setHistories] = useState<Partial<Record<ValuationMetric, ValuationHistory>>>({});
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

  const pbHistory = histories.pb_mcw ?? null;
  const peHistory = histories.pe_ttm_mcw ?? null;
  const pbSnapshot = metricSnapshot(valuation, "pb_mcw");
  const peSnapshot = metricSnapshot(valuation, "pe_ttm_mcw");
  const priceRange =
    prices && prices.bars.length > 0
      ? `${prices.bars[0].date} – ${prices.bars[prices.bars.length - 1].date}`
      : null;
  const lookup = pbHistory && peHistory ? buildPercentileLookup(pbHistory, peHistory) : null;
  const pctRange = lookup?.range() ?? null;

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
            <MetricReadout snapshot={pbSnapshot} label="PB" />
            <MetricReadout snapshot={peSnapshot} label="PE" />
          </div>

          {prices.bars.length > 0 && pbHistory && peHistory ? (
            <ValuationChart
              prices={prices}
              pbHistory={pbHistory}
              peHistory={peHistory}
              reloadKey={reloadKey + retryTick}
            />
          ) : (
            <div className="valuation-muted">暂无数据</div>
          )}

          <div className="range-note">
            <span>点数 {priceRange ?? "—"}</span>
            <span>分位 {pctRange ? `${pctRange[0]} – ${pctRange[1]}` : "—"}</span>
            <span>{hasChannel ? "悬浮看每个点位的 PB / PE 分位" : "不拟合回归通道"}</span>
          </div>
        </div>
      )}

      <div className="notes">
        <div className="note-item">
          图上只画指数点数（行情）；鼠标悬浮任意点位，会显示该日就近的 PB / PE
          分位——分位是相对自身历史估值的贵贱，不画走势，避免把两条线的起伏
          误读成因果。
          {hasChannel ? "价格走势与通道位置是两回事：通道位置还要叠加拟合出的轨道。" : "该指数不拟合回归通道，所以没有通道位置、轨道与趋势延伸。"}
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
