"use client";

/** 历史回溯 Tab：4 组固定窗口 + 全历史，默认单图展示。 */
import { useEffect, useState } from "react";
import TrendChart from "./TrendChart";
import { api } from "../lib/api";
import type { ChartData, HistoryOverview } from "../lib/types";

interface HistoryTabProps {
  overview: HistoryOverview;
  selected: string;
  onSelect: (stableId: string) => void;
  reloadKey: number;
}

interface LoadState {
  chart: ChartData | null;
  error: string | null;
  loading: boolean;
}

export default function HistoryTab({ overview, selected, onSelect, reloadKey }: HistoryTabProps) {
  const [state, setState] = useState<LoadState>({
    chart: null,
    error: null,
    loading: true,
  });
  const [retryTick, setRetryTick] = useState(0); // 重试用：URL 不变时也强制重跑加载

  const currentMeta =
    overview.windows.find((w) => w.stable_id === selected) ??
    (selected === "all" ? overview.all_history : null);

  useEffect(() => {
    if (!currentMeta) return;
    let cancelled = false;
    setState({ chart: null, error: null, loading: true });
    api
      .chart(currentMeta.model_id, "history")
      .then((chart) => {
        if (!cancelled) setState({ chart, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            chart: null,
            error: err instanceof Error ? err.message : "加载失败",
            loading: false,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentMeta?.model_id, retryTick, reloadKey]);

  const scopeText = (() => {
    if (!currentMeta) return "";
    if (selected === "all" && overview.all_history) {
      return `全样本拟合：${currentMeta.fit_start} 至 ${currentMeta.fit_end}（${overview.all_history.note}）`;
    }
    if ("window" in currentMeta) {
      return `固定窗口 ${currentMeta.window}：拟合 ${currentMeta.fit_start} 至 ${currentMeta.fit_end}（120个月），拟合后模型保持不变，右侧最多展示 36 个月后续价格`;
    }
    return "";
  })();

  return (
    <section>
      <div className="picker" role="tablist" aria-label="历史窗口选择">
        {overview.windows.map((w) => (
          <button
            key={w.stable_id}
            aria-current={selected === w.stable_id}
            onClick={() => onSelect(w.stable_id)}
          >
            窗口{w.window} {w.fit_start}–{w.fit_end}
          </button>
        ))}
        {overview.all_history && (
          <button
            aria-current={selected === "all"}
            onClick={() => onSelect("all")}
          >
            全历史 {overview.all_history.fit_start}–{overview.all_history.fit_end}
          </button>
        )}
      </div>

      <p className="range-note" style={{ borderTop: "none", padding: "4px 2px" }}>
        {scopeText}
      </p>

      {state.loading && <div className="message">图表加载中…</div>}
      {state.error && (
        <div className="message error">
          图表加载失败：{state.error}
          <br />
          <button className="retry-btn" onClick={() => setRetryTick((t) => t + 1)}>
            重试
          </button>
        </div>
      )}
      {state.chart && (
        <div className="chart-card">
          <TrendChart data={state.chart} chartId={`history-${selected}`} />
          <div className="range-note">
            <span>
              拟合区间 {state.chart.model.fit_start} – {state.chart.model.fit_end}
            </span>
            <span>拟合截止 {state.chart.fit_boundary_month}</span>
            <span>窗口 {state.chart.model.months} 个月</span>
            <span>通道宽度 {state.chart.model.multiplier}×deviation</span>
            {state.chart.extend_note && <span>{state.chart.extend_note}</span>}
          </div>
        </div>
      )}

      <div className="notes">
        <div className="note-item">
          每个固定窗口只用其 120 个月数据拟合；竖线右侧为拟合结束后的实际价格
          <span className="emphasis">观察区</span>，模型全程保持不变——后续价格不参与拟合。
        </div>
        <div className="note-item">
          「全历史」为全样本拟合：以全部历史数据拟合得到的通道，不能理解为在
          2005 年时点就已知的通道，也不构成样本外验证。
        </div>
        <div className="note-item">
          相邻窗口拟合区间重叠约 7 年，各窗口不是独立样本；通道描述历史波动范围，
          不预测未来。
        </div>
      </div>
    </section>
  );
}
